# -*- coding: utf-8 -*-
import logging

import pytest

import lambda_function as lf
from conftest import ExecuteCommandsDirective, RenderDocumentDirective, make_input
from jeedom_client import JeedomError

APIKEY = "cle-secrete-1234567890"


class FakeClient(object):
    """Routeur vocal du plugin simulé. `asked` : (phrase, délai) de chaque appel."""

    def __init__(self, reply="C'est fait", error=None, voice_results=None):
        self.voice_results = list(voice_results or [])
        self.error = error
        self.reply = reply
        self.voiced = []
        self.asked = []

    def voice(self, query, device_id="", person_id="", locale="", force_exact=False, timeout=6.0):
        self.voiced.append({"query": query, "device_id": device_id, "person_id": person_id,
                            "locale": locale, "force_exact": force_exact, "timeout": timeout})
        self.asked.append((query, timeout))
        if self.error:
            raise self.error
        return self.voice_results.pop(0) if self.voice_results else {"reply": self.reply, "matched": True}


@pytest.fixture
def setup():
    original_config, original_client = lf.CONFIG, lf._client

    def apply(client=None, **config):
        cfg = dict(original_config)
        cfg.update({
            "jeedom_url": "https://j.example",
            "jeedom_apikey": APIKEY,
            "keep_session_open": True,
            "keep_session_open_oneshot": False,
            "suppress_greeting": False,
            "jeedom_timeout": 6.5,
        })
        cfg.update(config)
        client = client or FakeClient()
        lf.configure(cfg, client)
        return client

    yield apply
    lf.configure(original_config, original_client)


def run(hi):
    return lf.lambda_handler(hi)


def query(text, **kwargs):
    return make_input(intent=lf.QUERY_INTENT, query=text, **kwargs)


class TestLaunch:
    def test_welcome_and_session_flag(self, setup):
        setup()
        hi = make_input("LaunchRequest")
        rb = run(hi)
        assert rb.speech == "Jeedom vous écoute. Que puis-je faire pour vous ?"
        assert rb.should_end is False
        assert hi.attributes_manager.session_attributes[lf.SESSION_CONVERSATION] is True
        assert rb.directives == []

    def test_apl_screen_with_dashboard_url(self, setup):
        setup(jeedom_dashboard="index.php?v=d&p=plan&plan_id=2")
        rb = run(make_input("LaunchRequest", apl=True))
        directive = rb.directives[0]
        assert isinstance(directive, RenderDocumentDirective)
        data = directive.datasources["jeedom"]
        assert data["url"] == "https://j.example/index.php?v=d&p=plan&plan_id=2"
        assert data["button"] == "Ouvrir Jeedom"
        assert directive.document["mainTemplate"]["parameters"] == ["payload"]

    def test_suppress_greeting(self, setup):
        setup(suppress_greeting=True)
        rb = run(make_input("LaunchRequest"))
        assert rb.speech is None
        assert rb.reprompt and rb.should_end is False

    def test_not_configured(self, setup):
        setup(jeedom_apikey="VOTRE-CLE-API-JEEDOM")
        rb = run(make_input("LaunchRequest"))
        assert "pas encore configuré" in rb.speech
        assert rb.should_end is True

class TestQuery:
    def test_one_shot_ends_session(self, setup):
        client = setup()
        rb = run(query("allume la cuisine"))
        assert client.asked[0][0] == "allume la cuisine"
        assert rb.speech == "C'est fait."
        assert rb.should_end is True

    def test_conversation_keeps_session(self, setup):
        setup()
        rb = run(query("allume la cuisine", session={lf.SESSION_CONVERSATION: True}))
        assert rb.should_end is False
        assert rb.reprompt == "Autre chose ?"

    def test_keep_session_disabled(self, setup):
        setup(keep_session_open=False)
        rb = run(query("allume la cuisine", session={lf.SESSION_CONVERSATION: True}))
        assert rb.should_end is True

    def test_one_shot_kept_open_with_option(self, setup):
        # Comportement de l'original (ask_for_further_commands=True).
        setup(keep_session_open_oneshot=True)
        rb = run(query("allume la cuisine"))
        assert rb.should_end is False
        assert rb.reprompt == "Autre chose ?"

    def test_one_shot_option_independent_of_conversation_option(self, setup):
        setup(keep_session_open=False, keep_session_open_oneshot=True)
        assert run(query("test")).should_end is False
        assert run(query("test", session={lf.SESSION_CONVERSATION: True})).should_end is True

    def test_exit_word(self, setup):
        client = setup()
        rb = run(query("non merci", session={lf.SESSION_CONVERSATION: True}))
        assert client.asked == []
        assert rb.should_end is True

    def test_empty_slot_asks_again(self, setup):
        client = setup()
        rb = run(query(None))
        assert client.asked == []
        assert rb.should_end is False

    def test_reply_is_escaped_for_ssml(self, setup):
        setup(FakeClient(reply="Tom & Jerry <ok>"))
        rb = run(query("test"))
        assert "&amp;" in rb.speech and "<" not in rb.speech

    def test_empty_reply(self, setup):
        setup(FakeClient(reply=""))
        assert run(query("test")).speech == "Jeedom n'a rien répondu."

    @pytest.mark.parametrize("kind, fragment", [
        ("timeout", "trop de temps"),
        ("unreachable", "joindre votre Jeedom"),
        ("auth", "refusé la clé API"),
        ("error", "n'a pas pu traiter"),
    ])
    def test_errors_have_clear_message(self, setup, kind, fragment):
        setup(FakeClient(error=JeedomError(kind, "détail")))
        assert fragment in run(query("test")).speech

    def test_timeout_respects_lambda_remaining_time(self, setup):
        client = setup(jeedom_timeout=6.5)
        run(query("test", lambda_ms=3000))
        assert client.asked[0][1] <= 3.0 - lf.RESPONSE_RESERVE + 0.05

    def test_timeout_uses_config_when_lambda_has_time(self, setup):
        client = setup(jeedom_timeout=5.0)
        run(query("test", lambda_ms=60000))
        assert 4.5 < client.asked[0][1] <= 5.0

    def test_english_locale(self, setup):
        setup(FakeClient(reply="Living room 21.5 °C"))
        assert run(query("temperature", locale="en-US")).speech == "Living room 21.5 °C."

    def test_api_key_never_logged(self, setup, caplog):
        setup(FakeClient(error=JeedomError("auth", "-32002 refusé")))
        with caplog.at_level(logging.DEBUG):
            run(query("allume"))
        assert caplog.records
        assert APIKEY not in caplog.text


class TestReplyScreen:
    def test_reply_shown_on_screen_device(self, setup):
        setup(FakeClient(reply="Salon : 21.5 °C & sec <3"))
        rb = run(query("température salon", apl=True))
        assert len(rb.directives) == 1
        directive = rb.directives[0]
        assert isinstance(directive, RenderDocumentDirective)
        data = directive.datasources["jeedom"]
        assert data["welcome"] == "Salon : 21,5 °C &amp; sec &lt;3."
        assert data["hint"] == ""
        assert data["url"] == "https://j.example/index.php?v=m"

    def test_no_directive_without_screen(self, setup):
        setup()
        assert run(query("température salon")).directives == []

    def test_error_and_choice_shown_too(self, setup):
        setup(FakeClient(error=JeedomError("timeout", "voiceRouter")))
        rb = run(query("x", apl=True))
        assert "trop de temps" in rb.directives[0].datasources["jeedom"]["welcome"]
        setup(FakeClient(voice_results=[AMBIGUOUS]))
        rb = run(query("allume", apl=True))
        assert "Laquelle" in rb.directives[0].datasources["jeedom"]["welcome"]

    def test_launch_screen_keeps_hint(self, setup):
        setup()
        data = run(make_input("LaunchRequest", apl=True)).directives[0].datasources["jeedom"]
        assert data["welcome"] == "Bienvenue à la maison !"
        assert data["hint"].startswith("Touchez le bouton")


class TestDashboard:
    def test_open_on_screen_device(self, setup):
        client = setup(jeedom_dashboard="index.php?v=m&p=home")
        rb = run(query("ouvre jeedom", apl=True))
        assert client.asked == []
        render, execute = rb.directives
        assert isinstance(render, RenderDocumentDirective)
        assert isinstance(execute, ExecuteCommandsDirective)
        assert execute.commands[0].source == "https://j.example/index.php?v=m&p=home"
        assert render.token == execute.token
        assert rb.speech == "J'ouvre Jeedom"

    def test_not_configured_before_opening(self, setup):
        setup(jeedom_url="")
        rb = run(query("ouvre jeedom", apl=True))
        assert rb.directives == []
        assert "pas encore configuré" in rb.speech

    def test_no_screen(self, setup):
        setup()
        rb = run(query("ouvre le tableau de bord", apl=False))
        assert rb.directives == []
        assert "pas d'écran" in rb.speech

    def test_apl_detected_per_request_not_shared(self, setup):
        # L'original gardait is_apl_supported en global : un Echo Show ouvrait
        # le skill, puis un Echo Dot recevait des directives APL.
        setup()
        run(make_input("LaunchRequest", apl=True))
        rb = run(query("ouvre jeedom", apl=False))
        assert rb.directives == []


class TestBuiltIns:
    @pytest.mark.parametrize("intent", ["AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.NavigateHomeIntent"])
    def test_exit_intents(self, setup, intent):
        setup()
        rb = run(make_input(intent=intent))
        assert rb.should_end is True
        assert rb.speech

    def test_help(self, setup):
        setup()
        rb = run(make_input(intent="AMAZON.HelpIntent"))
        assert rb.should_end is False

    def test_fallback(self, setup):
        setup()
        rb = run(make_input(intent="AMAZON.FallbackIntent"))
        assert "pas compris" in rb.speech
        assert rb.should_end is False

    def test_session_ended(self, setup):
        setup()
        rb = run(make_input("SessionEndedRequest"))
        assert rb.speech is None

    def test_unexpected_exception(self, setup, monkeypatch):
        setup()

        def boom(*args, **kwargs):
            raise KeyError("x")

        monkeypatch.setattr(lf.Turn, "ask_jeedom", boom)
        rb = run(query("test"))
        assert "n'a pas pu traiter" in rb.speech


AMBIGUOUS = {"reply": "J'ai trouvé plusieurs commandes proches. 1 : salon, 2 : cuisine. Laquelle ?",
             "matched": False, "ambiguous": True, "options": ["allume salon", "allume cuisine"]}
UNSURE = {"reply": "Je ne suis pas sûr. Veux-tu dire : Lampe salon On ? Dis oui pour confirmer.",
          "matched": False, "ambiguous": True, "options": ["lampe salon on"]}


class TestVoiceRouter:
    def test_device_locale_person_sent(self, setup):
        client = setup()
        rb = run(query("éteins tout", locale="fr-CA", person="amzn1.ask.person.P"))
        call = client.voiced[0]
        assert call["query"] == "éteins tout" and call["force_exact"] is False
        assert call["device_id"] == "amzn1.ask.device.TEST"
        assert call["locale"] == "fr-CA" and call["person_id"] == "amzn1.ask.person.P"
        assert rb.speech == "C'est fait."

    def test_async_ack_is_spoken(self, setup):
        setup(FakeClient(voice_results=[{"reply": "Je m'en occupe.", "matched": True, "route": "async"}]))
        assert run(query("résume la maison")).speech == "Je m'en occupe."

    @pytest.mark.parametrize("route, reply", [
        ("async", "Je m'en occupe."),
        ("blocked", "Cet appareil n'est pas autorisé à piloter la maison."),
    ])
    def test_route_closes_conversation(self, setup, route, reply):
        setup(FakeClient(voice_results=[{"reply": reply, "matched": route == "async", "route": route}]))
        rb = run(query("résume la maison", session={lf.SESSION_CONVERSATION: True}))
        assert rb.speech == reply
        assert rb.should_end is True and rb.reprompt is None

    def test_route_closes_session_after_choice(self, setup):
        setup(FakeClient(voice_results=[{"reply": "Je m'en occupe.", "matched": True, "route": "async"}]))
        rb = run(query("deux", session={lf.SESSION_CONVERSATION: True, lf.SESSION_OPTIONS: ["a", "b"]}))
        assert rb.should_end is True

    def test_other_routes_keep_conversation(self, setup):
        setup(FakeClient(voice_results=[{"reply": "Il fait 21 °C", "matched": True, "route": "voiceQuery"}]))
        rb = run(query("température", session={lf.SESSION_CONVERSATION: True}))
        assert rb.should_end is False

    @pytest.mark.parametrize("kind, text", [("timeout", "trop de temps"), ("auth", ""), ("error", "")])
    def test_error_is_spoken_without_retry(self, setup, kind, text):
        client = setup(FakeClient(error=JeedomError(kind, "voiceRouter")))
        rb = run(query("x"))
        assert len(client.voiced) == 1
        assert rb.speech and text in rb.speech


class TestChoices:
    def test_ambiguous_keeps_options_and_session(self, setup):
        setup(FakeClient(voice_results=[AMBIGUOUS]))
        hi = query("allume")
        rb = run(hi)
        assert hi.attributes_manager.session_attributes[lf.SESSION_OPTIONS] == AMBIGUOUS["options"]
        assert rb.should_end is False
        assert rb.reprompt == "Dites oui, ou le numéro de votre choix."

    def test_number_resends_option_with_force_exact(self, setup):
        client = setup(FakeClient(voice_results=[{"reply": "Cuisine allumée", "matched": True}]))
        hi = query("deux", session={lf.SESSION_OPTIONS: AMBIGUOUS["options"]})
        rb = run(hi)
        assert client.voiced[0]["query"] == "allume cuisine"
        assert client.voiced[0]["force_exact"] is True
        assert lf.SESSION_OPTIONS not in hi.attributes_manager.session_attributes
        assert rb.speech == "Cuisine allumée."
        assert rb.should_end is True  # demande directe

    def test_yes_confirms_single_option(self, setup):
        client = setup()
        run(make_input(intent="AMAZON.YesIntent", session={lf.SESSION_OPTIONS: UNSURE["options"]}))
        assert client.voiced[0]["query"] == "lampe salon on"
        assert client.voiced[0]["force_exact"] is True

    def test_yes_with_several_options_asks_number(self, setup):
        client = setup()
        hi = make_input(intent="AMAZON.YesIntent", session={lf.SESSION_OPTIONS: AMBIGUOUS["options"]})
        rb = run(hi)
        assert client.voiced == []
        assert hi.attributes_manager.session_attributes[lf.SESSION_OPTIONS] == AMBIGUOUS["options"]
        assert rb.speech == "Dites oui, ou le numéro de votre choix."

    @pytest.mark.parametrize("hi_factory", [
        lambda: make_input(intent="AMAZON.NoIntent", session={lf.SESSION_OPTIONS: ["a"]}),
        lambda: query("non", session={lf.SESSION_OPTIONS: ["a"]}),
    ])
    def test_no_cancels(self, setup, hi_factory):
        client = setup()
        hi = hi_factory()
        rb = run(hi)
        assert client.voiced == []
        assert rb.speech == "D'accord, rien n'est fait."
        assert lf.SESSION_OPTIONS not in hi.attributes_manager.session_attributes

    def test_no_without_pending_choice_says_goodbye(self, setup):
        setup()
        rb = run(make_input(intent="AMAZON.NoIntent"))
        assert rb.should_end is True

    def test_yes_without_pending_choice_helps(self, setup):
        setup()
        rb = run(make_input(intent="AMAZON.YesIntent"))
        assert rb.should_end is False

    def test_new_sentence_replaces_pending_choice(self, setup):
        client = setup()
        hi = query("ferme les volets du salon", session={lf.SESSION_OPTIONS: AMBIGUOUS["options"]})
        run(hi)
        assert client.voiced[0]["query"] == "ferme les volets du salon"
        assert client.voiced[0]["force_exact"] is False
        assert lf.SESSION_OPTIONS not in hi.attributes_manager.session_attributes

    def test_choice_inside_conversation_keeps_session(self, setup):
        setup()
        rb = run(query("1", session={lf.SESSION_OPTIONS: AMBIGUOUS["options"], lf.SESSION_CONVERSATION: True}))
        assert rb.should_end is False
