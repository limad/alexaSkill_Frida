# -*- coding: utf-8 -*-
"""Skill Alexa « Frida » : envoie la phrase de l'utilisateur aux interactions Jeedom.

Adapté de HomeAssistantAssist (https://github.com/fabianosan/HomeAssistantAssist)
de Fabiano Santos — voir README.md.

Organisation :
- `configure()` prépare une fois par conteneur Lambda tout ce qui ne dépend que de
  config.cfg (erreurs de config, URL du dashboard, client Jeedom) ;
- `Turn` regroupe ce qui dépend de la requête (langue, textes, réponse) ;
- les handlers ne font que choisir quoi répondre.
"""
import json
import logging
import os
import random
import time

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_model.interfaces.alexa.presentation.apl import (
    ExecuteCommandsDirective,
    OpenUrlCommand,
    RenderDocumentDirective,
)

import helpers
from jeedom_client import JeedomClient, JeedomError

QUERY_INTENT = "JeedomQueryIntent"
APL_TOKEN = "jeedomAssist"
# Marge laissée à la Lambda pour construire et renvoyer la réponse.
RESPONSE_RESERVE = 0.8
# Clé de session : la conversation a été ouverte par « Alexa, ouvre … ».
SESSION_CONVERSATION = "conversation"

ERROR_TEXT_KEYS = {
    "timeout": "alexa_speak_timeout",
    "unreachable": "alexa_speak_unreachable",
    "auth": "alexa_speak_auth_error",
    "error": "alexa_speak_error",
}

logger = logging.getLogger(__name__)


def load_json(name):
    with open(os.path.join(helpers.BASE_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# Documents APL lus une fois (jamais modifiés : les textes passent par datasources).
APL_DASHBOARD = load_json("apl_dashboard.json")
APL_EMPTY = load_json("apl_empty.json")

CONFIG = {}
CONFIG_ERRORS = []
DASHBOARD_URL = ""
_client = None


def configure(config, client=None):
    """Applique une configuration (au démarrage, ou dans les tests)."""
    global CONFIG, CONFIG_ERRORS, DASHBOARD_URL, _client
    CONFIG = config
    CONFIG_ERRORS = helpers.config_errors(config)
    DASHBOARD_URL = helpers.dashboard_url(config["jeedom_url"], config["jeedom_dashboard"])
    _client = client
    logger.setLevel(logging.DEBUG if config["debug"] else logging.INFO)


def get_client():
    """Client Jeedom partagé (sans état utilisateur : seule la connexion HTTP est réutilisée)."""
    global _client
    if _client is None:
        _client = JeedomClient(
            CONFIG["jeedom_url"],
            CONFIG["jeedom_apikey"],
            profile=CONFIG["jeedom_profile"],
            verify_ssl=CONFIG["verify_ssl"],
        )
    return _client


configure(helpers.load_config(os.path.join(helpers.BASE_DIR, "config.cfg")))


class Deadline(object):
    """Budget de temps de la requête en cours (délai config et temps Lambda restant)."""

    def __init__(self, handler_input, total):
        self.end = time.monotonic() + total
        lambda_context = getattr(handler_input, "context", None)
        try:
            remaining = lambda_context.get_remaining_time_in_millis() / 1000.0
            self.end = min(self.end, time.monotonic() + remaining - RESPONSE_RESERVE)
        except Exception:
            pass

    def remaining(self, cap=None):
        left = self.end - time.monotonic()
        if cap is not None:
            left = min(left, cap)
        return max(left, 0.3)


# --------------------------------------------------------------------------
# Requête en cours
# --------------------------------------------------------------------------
class Turn(object):
    """Une requête Alexa : langue, textes, appareil, session et constructeur de réponse."""

    def __init__(self, handler_input):
        self.handler_input = handler_input
        self.builder = handler_input.response_builder
        request = handler_input.request_envelope.request
        self.locale = getattr(request, "locale", None) or helpers.DEFAULT_LOCALE
        self.texts = helpers.load_locale(self.locale)
        self.session = handler_input.attributes_manager.session_attributes

    @property
    def has_screen(self):
        """Détecté à chaque requête : l'appareil qui parle est celui qui compte."""
        try:
            device = self.handler_input.request_envelope.context.system.device
            return device.supported_interfaces.alexa_presentation_apl is not None
        except AttributeError:
            return False

    def slot(self, name):
        try:
            slot = self.handler_input.request_envelope.request.intent.slots.get(name)
            return (slot.value or "").strip() if slot else ""
        except AttributeError:
            return ""

    # Réponses -------------------------------------------------------------
    def say(self, text, keep_open, reprompt=None):
        self.builder.speak(helpers.ssml_safe(text))
        if keep_open:
            self.builder.ask(helpers.ssml_safe(reprompt or self.texts["alexa_speak_question"]))
        else:
            self.builder.set_should_end_session(True)
        return self.builder.response

    def say_key(self, key, keep_open, reprompt_key=None):
        reprompt = self.texts[reprompt_key] if reprompt_key else None
        return self.say(self.texts[key], keep_open, reprompt)

    def goodbye(self):
        return self.say(random.choice(helpers.split_list(self.texts["alexa_speak_exit"])), keep_open=False)

    def not_configured(self):
        """Réponse « skill non configuré », ou None si config.cfg est complet."""
        if not CONFIG_ERRORS:
            return None
        logger.error("config.cfg incomplet, à renseigner : %s", ", ".join(CONFIG_ERRORS))
        return self.say_key("alexa_speak_not_configured", keep_open=False)

    # Jeedom ---------------------------------------------------------------
    def ask_jeedom(self, query, deadline):
        """Phrase -> Jeedom -> texte prêt à être dit (message clair en cas d'erreur)."""
        try:
            reply = get_client().ask(query, timeout=deadline.remaining())
        except JeedomError as e:
            logger.error("Appel Jeedom en échec (%s) : %s", e.kind, e.detail)
            return self.texts[ERROR_TEXT_KEYS.get(e.kind, "alexa_speak_error")]
        logger.debug("Réponse Jeedom : %s", reply[:300])
        return helpers.clean_for_speech(reply, self.locale) or self.texts["alexa_speak_empty"]

    # Écran ----------------------------------------------------------------
    def show_home_screen(self):
        self.builder.add_directive(RenderDocumentDirective(
            token=APL_TOKEN,
            document=APL_DASHBOARD,
            datasources={"jeedom": {
                "title": self.texts["echo_screen_title"],
                "welcome": self.texts["echo_screen_welcome_text"],
                "hint": self.texts["echo_screen_click_text"],
                "button": self.texts["echo_screen_button_text"],
                "url": DASHBOARD_URL,
            }},
        ))

    def open_dashboard(self):
        if not self.has_screen:
            return self.say_key("alexa_speak_no_screen", keep_open=False)
        # OpenURL a besoin d'un document APL affiché : on rend un document vide.
        self.builder.add_directive(RenderDocumentDirective(token=APL_TOKEN, document=APL_EMPTY))
        self.builder.add_directive(ExecuteCommandsDirective(
            token=APL_TOKEN, commands=[OpenUrlCommand(source=DASHBOARD_URL)]))
        self.builder.speak(helpers.ssml_safe(self.texts["alexa_speak_open_dashboard"]))
        return self.builder.response


def consume_prompt(deadline):
    """Phrase déposée dans une variable Jeedom pour démarrer la conversation ('' sinon)."""
    name = CONFIG["jeedom_prompt_variable"]
    if not name:
        return ""
    client = get_client()
    try:
        prompt = client.read_variable(name, timeout=deadline.remaining(cap=2.0))
    except JeedomError as e:
        logger.error("Lecture de la variable de démarrage impossible (%s) : %s", e.kind, e.detail)
        return ""
    if not prompt or prompt.lower() == "none":
        return ""
    try:
        # Vidée tout de suite : la phrase ne doit servir qu'une fois.
        client.write_variable(name, "", timeout=deadline.remaining(cap=1.5))
    except JeedomError as e:
        logger.warning("Variable de démarrage non vidée (%s) : %s", e.kind, e.detail)
    return prompt


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        turn = Turn(handler_input)
        failure = turn.not_configured()
        if failure:
            return failure
        turn.session[SESSION_CONVERSATION] = True
        deadline = Deadline(handler_input, CONFIG["jeedom_timeout"])

        prompt = consume_prompt(deadline)
        if prompt:
            logger.info("Démarrage avec la phrase de la variable Jeedom")
            return turn.say(turn.ask_jeedom(prompt, deadline), keep_open=True)

        if turn.has_screen:
            turn.show_home_screen()
        if CONFIG["suppress_greeting"]:
            turn.builder.ask(helpers.ssml_safe(turn.texts["alexa_speak_help"]))
            return turn.builder.response
        return turn.say_key("alexa_speak_welcome_message", keep_open=True, reprompt_key="alexa_speak_help")


class QueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name(QUERY_INTENT)(handler_input)

    def handle(self, handler_input):
        turn = Turn(handler_input)
        query = turn.slot("query")
        if not query:
            return turn.say_key("alexa_speak_help", keep_open=True)
        logger.info("Phrase reçue : %s", query)

        if helpers.is_exit_request(query, turn.texts["keywords_to_close_skill"]):
            return turn.goodbye()
        failure = turn.not_configured()
        if failure:
            return failure
        if helpers.matches_keyword(query, turn.texts["keywords_to_open_dashboard"]):
            return turn.open_dashboard()

        speech = turn.ask_jeedom(query, Deadline(handler_input, CONFIG["jeedom_timeout"]))
        # Conversation (« Alexa, ouvre … ») : keep_session_open.
        # Demande directe (« Alexa, demande à … de … ») : keep_session_open_oneshot.
        if turn.session.get(SESSION_CONVERSATION):
            return turn.say(speech, keep_open=CONFIG["keep_session_open"])
        return turn.say(speech, keep_open=CONFIG["keep_session_open_oneshot"])


class SpeechIntentHandler(AbstractRequestHandler):
    """Intention qui répond par un texte fixe et garde la session ouverte (aide, incompris)."""

    def __init__(self, intent, text_key):
        self.matches = ask_utils.is_intent_name(intent)
        self.text_key = text_key

    def can_handle(self, handler_input):
        return self.matches(handler_input)

    def handle(self, handler_input):
        return Turn(handler_input).say_key(self.text_key, keep_open=True, reprompt_key="alexa_speak_help")


class ExitIntentHandler(AbstractRequestHandler):
    INTENTS = ("AMAZON.CancelIntent", "AMAZON.StopIntent", "AMAZON.NavigateHomeIntent")

    def __init__(self):
        self.matchers = [ask_utils.is_intent_name(name) for name in self.INTENTS]

    def can_handle(self, handler_input):
        return any(match(handler_input) for match in self.matchers)

    def handle(self, handler_input):
        return Turn(handler_input).goodbye()


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error("Erreur inattendue : %s", type(exception).__name__, exc_info=True)
        return Turn(handler_input).say_key("alexa_speak_error", keep_open=True, reprompt_key="alexa_speak_help")


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(QueryIntentHandler())
sb.add_request_handler(SpeechIntentHandler("AMAZON.HelpIntent", "alexa_speak_help"))
sb.add_request_handler(SpeechIntentHandler("AMAZON.FallbackIntent", "alexa_speak_fallback"))
sb.add_request_handler(ExitIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())
lambda_handler = sb.lambda_handler()
