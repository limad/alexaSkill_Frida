# -*- coding: utf-8 -*-
"""Stubs ask-sdk : les tests tournent sans le SDK Alexa installé."""
import os
import sys
import types

import pytest

LAMBDA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda")
sys.path.insert(0, LAMBDA_DIR)


# --------------------------------------------------------------------------
# Faux modules ask_sdk_core / ask_sdk_model
# --------------------------------------------------------------------------
class AbstractRequestHandler(object):
    pass


class AbstractExceptionHandler(object):
    pass


class SkillBuilder(object):
    def __init__(self):
        self.request_handlers = []
        self.exception_handlers = []

    def add_request_handler(self, handler):
        self.request_handlers.append(handler)

    def add_exception_handler(self, handler):
        self.exception_handlers.append(handler)

    def lambda_handler(self):
        builder = self

        def handler(handler_input, context=None):
            try:
                for h in builder.request_handlers:
                    if h.can_handle(handler_input):
                        return h.handle(handler_input)
                raise RuntimeError("aucun handler")
            except Exception as e:  # même comportement que le SDK
                for h in builder.exception_handlers:
                    if h.can_handle(handler_input, e):
                        return h.handle(handler_input, e)
                raise

        return handler


def is_request_type(name):
    return lambda hi: hi.request_envelope.request.object_type == name


def is_intent_name(name):
    def check(hi):
        req = hi.request_envelope.request
        return req.object_type == "IntentRequest" and req.intent.name == name

    return check


class _Directive(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class RenderDocumentDirective(_Directive):
    pass


class ExecuteCommandsDirective(_Directive):
    pass


class OpenUrlCommand(_Directive):
    pass


def _install_stubs():
    def module(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod
        return mod

    module("ask_sdk_core")
    module("ask_sdk_core.utils", is_request_type=is_request_type, is_intent_name=is_intent_name)
    module("ask_sdk_core.skill_builder", SkillBuilder=SkillBuilder)
    module("ask_sdk_core.dispatch_components",
           AbstractRequestHandler=AbstractRequestHandler,
           AbstractExceptionHandler=AbstractExceptionHandler)
    for name in ("ask_sdk_model", "ask_sdk_model.interfaces", "ask_sdk_model.interfaces.alexa",
                 "ask_sdk_model.interfaces.alexa.presentation"):
        module(name)
    module("ask_sdk_model.interfaces.alexa.presentation.apl",
           RenderDocumentDirective=RenderDocumentDirective,
           ExecuteCommandsDirective=ExecuteCommandsDirective,
           OpenUrlCommand=OpenUrlCommand)


_install_stubs()


# --------------------------------------------------------------------------
# Faux HandlerInput
# --------------------------------------------------------------------------
class ResponseBuilder(object):
    def __init__(self):
        self.speech = None
        self.reprompt = None
        self.should_end = None
        self.directives = []

    def speak(self, text):
        self.speech = text
        return self

    def ask(self, text):
        self.reprompt = text
        self.should_end = False
        return self

    def set_should_end_session(self, value):
        self.should_end = value
        return self

    def add_directive(self, directive):
        self.directives.append(directive)
        return self

    @property
    def response(self):
        return self


class Slot(object):
    def __init__(self, value):
        self.value = value


class LambdaContext(object):
    def __init__(self, remaining_ms):
        self.remaining_ms = remaining_ms

    def get_remaining_time_in_millis(self):
        return self.remaining_ms


def make_input(request_type="IntentRequest", intent=None, query=None, locale="fr-FR",
               apl=False, session=None, lambda_ms=None, person=None):
    slots = {"query": Slot(query)} if intent else {}
    request = types.SimpleNamespace(
        object_type=request_type,
        locale=locale,
        intent=types.SimpleNamespace(name=intent, slots=slots) if intent else None,
    )
    interfaces = types.SimpleNamespace(alexa_presentation_apl=object() if apl else None)
    device = types.SimpleNamespace(device_id="amzn1.ask.device.TEST", supported_interfaces=interfaces)
    person_ns = types.SimpleNamespace(person_id=person) if person else None
    context = types.SimpleNamespace(system=types.SimpleNamespace(device=device, person=person_ns))
    return types.SimpleNamespace(
        request_envelope=types.SimpleNamespace(request=request, context=context),
        response_builder=ResponseBuilder(),
        attributes_manager=types.SimpleNamespace(session_attributes=dict(session or {})),
        context=LambdaContext(lambda_ms) if lambda_ms is not None else None,
    )


@pytest.fixture
def handler_input():
    return make_input
