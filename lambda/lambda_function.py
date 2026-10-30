# -*- coding: utf-8 -*-
"""Skill Alexa « Jeedom Assist » : envoie la phrase de l'utilisateur aux interactions Jeedom.

Adapté de HomeAssistantAssist (https://github.com/fabianosan/HomeAssistantAssist)
de Fabiano Santos — voir README.md.
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

CONFIG = helpers.load_config(os.path.join(helpers.BASE_DIR, "config.cfg"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if CONFIG["debug"] else logging.INFO)

ERROR_TEXT_KEYS = {
    "timeout": "alexa_speak_timeout",
    "unreachable": "alexa_speak_unreachable",
    "auth": "alexa_speak_auth_error",
    "error": "alexa_speak_error",
}

_client = None


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


def load_json(name):
    with open(os.path.join(helpers.BASE_DIR, name), encoding="utf-8") as f:
        return json.load(f)


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
# Lecture de la requête Alexa
# --------------------------------------------------------------------------
def request_locale(handler_input):
    return getattr(handler_input.request_envelope.request, "locale", None) or helpers.DEFAULT_LOCALE


def texts_for(handler_input):
    return helpers.load_locale(request_locale(handler_input))


def supports_apl(handler_input):
    """Détecté à chaque requête : l'appareil qui parle est celui qui compte."""
    try:
        device = handler_input.request_envelope.context.system.device
        return device.supported_interfaces.alexa_presentation_apl is not None
    except AttributeError:
        return False


def slot_value(handler_input, name):
    try:
        slot = handler_input.request_envelope.request.intent.slots.get(name)
        return (slot.value or "").strip() if slot else ""
    except AttributeError:
        return ""


def session_attributes(handler_input):
    return handler_input.attributes_manager.session_attributes


# --------------------------------------------------------------------------
# Réponses
# --------------------------------------------------------------------------
def respond(handler_input, text, keep_open, reprompt=None):
    builder = handler_input.response_builder
    builder.speak(helpers.ssml_safe(text))
    if keep_open:
        builder.ask(helpers.ssml_safe(reprompt or texts_for(handler_input)["alexa_speak_question"]))
    else:
        builder.set_should_end_session(True)
    return builder.response


def goodbye(handler_input):
    text = random.choice(helpers.split_list(texts_for(handler_input)["alexa_speak_exit"]))
    return respond(handler_input, text, keep_open=False)


def ask_jeedom(handler_input, query, deadline):
    """Phrase -> Jeedom -> texte prêt à être dit (message clair en cas d'erreur)."""
    texts = texts_for(handler_input)
    try:
        reply = get_client().ask(query, timeout=deadline.remaining())
    except JeedomError as e:
        logger.error("Appel Jeedom en échec (%s) : %s", e.kind, e.detail)
        return texts[ERROR_TEXT_KEYS.get(e.kind, "alexa_speak_error")]
    logger.debug("Réponse Jeedom : %s", reply[:300])
    return helpers.clean_for_speech(reply, request_locale(handler_input)) or texts["alexa_speak_empty"]


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


def dashboard_apl(texts):
    return RenderDocumentDirective(
        token=APL_TOKEN,
        document=load_json("apl_dashboard.json"),
        datasources={
            "jeedom": {
                "title": texts["echo_screen_title"],
                "welcome": texts["echo_screen_welcome_text"],
                "hint": texts["echo_screen_click_text"],
                "button": texts["echo_screen_button_text"],
                "url": helpers.dashboard_url(CONFIG["jeedom_url"], CONFIG["jeedom_dashboard"]),
            }
        },
    )


def open_dashboard(handler_input):
    texts = texts_for(handler_input)
    if not supports_apl(handler_input):
        return respond(handler_input, texts["alexa_speak_no_screen"], keep_open=False)
    url = helpers.dashboard_url(CONFIG["jeedom_url"], CONFIG["jeedom_dashboard"])
    builder = handler_input.response_builder
    # OpenURL a besoin d'un document APL affiché : on rend un document vide.
    builder.add_directive(RenderDocumentDirective(token=APL_TOKEN, document=load_json("apl_empty.json")))
    builder.add_directive(ExecuteCommandsDirective(token=APL_TOKEN, commands=[OpenUrlCommand(source=url)]))
    builder.speak(helpers.ssml_safe(texts["alexa_speak_open_dashboard"]))
    return builder.response


def not_configured(handler_input):
    errors = helpers.config_errors(CONFIG)
    if not errors:
        return None
    logger.error("config.cfg incomplet, à renseigner : %s", ", ".join(errors))
    return respond(handler_input, texts_for(handler_input)["alexa_speak_not_configured"], keep_open=False)


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------
class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        failure = not_configured(handler_input)
        if failure:
            return failure
        texts = texts_for(handler_input)
        session_attributes(handler_input)[SESSION_CONVERSATION] = True
        deadline = Deadline(handler_input, CONFIG["jeedom_timeout"])

        prompt = consume_prompt(deadline)
        if prompt:
            logger.info("Démarrage avec la phrase de la variable Jeedom")
            return respond(handler_input, ask_jeedom(handler_input, prompt, deadline), keep_open=True)

        if supports_apl(handler_input):
            handler_input.response_builder.add_directive(dashboard_apl(texts))
        if CONFIG["suppress_greeting"]:
            handler_input.response_builder.ask(helpers.ssml_safe(texts["alexa_speak_help"]))
            return handler_input.response_builder.response
        return respond(handler_input, texts["alexa_speak_welcome_message"], keep_open=True,
                       reprompt=texts["alexa_speak_help"])


class QueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name(QUERY_INTENT)(handler_input)

    def handle(self, handler_input):
        texts = texts_for(handler_input)
        query = slot_value(handler_input, "query")
        if not query:
            return respond(handler_input, texts["alexa_speak_help"], keep_open=True)
        logger.info("Phrase reçue : %s", query)

        if helpers.is_exit_request(query, helpers.split_list(texts["keywords_to_close_skill"])):
            return goodbye(handler_input)
        if helpers.matches_keyword(query, helpers.split_list(texts["keywords_to_open_dashboard"])):
            return open_dashboard(handler_input)

        failure = not_configured(handler_input)
        if failure:
            return failure
        deadline = Deadline(handler_input, CONFIG["jeedom_timeout"])
        speech = ask_jeedom(handler_input, query, deadline)
        # Session gardée ouverte seulement dans une conversation (« Alexa, ouvre … »).
        # Une demande directe (« Alexa, demande à … de … ») se termine après la réponse.
        conversation = bool(session_attributes(handler_input).get(SESSION_CONVERSATION))
        return respond(handler_input, speech, keep_open=CONFIG["keep_session_open"] and conversation)


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        texts = texts_for(handler_input)
        return respond(handler_input, texts["alexa_speak_help"], keep_open=True, reprompt=texts["alexa_speak_help"])


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        texts = texts_for(handler_input)
        return respond(handler_input, texts["alexa_speak_fallback"], keep_open=True, reprompt=texts["alexa_speak_help"])


class ExitIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.NavigateHomeIntent")(handler_input))

    def handle(self, handler_input):
        return goodbye(handler_input)


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
        texts = texts_for(handler_input)
        return respond(handler_input, texts["alexa_speak_error"], keep_open=True, reprompt=texts["alexa_speak_help"])


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(QueryIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(ExitIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())
lambda_handler = sb.lambda_handler()
