# -*- coding: utf-8 -*-
import logging

import pytest

import lambda_function as lf
from conftest import ExecuteCommandsDirective, RenderDocumentDirective, make_input
from jeedom_client import JeedomError

APIKEY = "cle-secrete-1234567890"


class FakeClient(object):
    def __init__(self, reply="C'est fait", error=None, variable="", read_error=None, write_error=None):
        self.reply = reply
        self.error = error
        self.variable = variable
        self.read_error = read_error
        self.write_error = write_error
        self.asked = []
        self.written = []

    def ask(self, query, timeout=6.0):
        self.asked.append((query, timeout))
        if self.error:
            raise self.error
        return self.reply

    def read_variable(self, name, timeout=2.0):
        if self.read_error:
            raise self.read_error
        return self.variable

    def write_variable(self, name, value, timeout=2.0):
        if self.write_error:
            raise self.write_error
        self.written.append((name, value))


@pytest.fixture
def setup(monkeypatch):
    def apply(client=None, **config):
        cfg = dict(lf.CONFIG)
        cfg.update({
            "jeedom_url": "https://j.example",
            "jeedom_apikey": APIKEY,
            "jeedom_prompt_variable": "",
            "keep_session_open": True,
            "suppress_greeting": False,
            "jeedom_timeout": 6.5,
        })
        cfg.update(config)
        monkeypatch.setattr(lf, "CONFIG", cfg)
        client = client or FakeClient()
        monkeypatch.setattr(lf, "_client", client)
        return client

    return apply


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

    def test_prompt_variable_used_once(self, setup):
        client = setup(FakeClient(reply="Il fait 21.5 °C", variable="quelle température"),
                       jeedom_prompt_variable="alexa_prompt")
        rb = run(make_input("LaunchRequest"))
        assert client.asked[0][0] == "quelle température"
        assert client.written == [("alexa_prompt", "")]
        assert rb.speech == "Il fait 21,5 °C."
        assert rb.should_end is False

    @pytest.mark.parametrize("value", ["", "none", "None"])
    def test_empty_prompt_variable_ignored(self, setup, value):
        client = setup(FakeClient(variable=value), jeedom_prompt_variable="alexa_prompt")
        rb = run(make_input("LaunchRequest"))
        assert client.asked == []
        assert rb.speech.startswith("Jeedom vous écoute")

    def test_prompt_read_error_falls_back_to_welcome(self, setup):
        client = setup(FakeClient(read_error=JeedomError("auth", "-32701")), jeedom_prompt_variable="alexa_prompt")
        rb = run(make_input("LaunchRequest"))
        assert client.asked == []
        assert rb.speech.startswith("Jeedom vous écoute")

    def test_prompt_write_error_still_answers(self, setup):
        client = setup(FakeClient(variable="bonjour", write_error=JeedomError("auth", "-32701")),
                       jeedom_prompt_variable="alexa_prompt")
        run(make_input("LaunchRequest"))
        assert client.asked[0][0] == "bonjour"


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

        monkeypatch.setattr(lf, "ask_jeedom", boom)
        rb = run(query("test"))
        assert "n'a pas pu traiter" in rb.speech
