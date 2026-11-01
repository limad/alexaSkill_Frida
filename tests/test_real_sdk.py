# -*- coding: utf-8 -*-
"""Contrôle avec le vrai ask-sdk-core (sauté s'il n'est pas installé).

Lancé dans un sous-processus pour ne pas croiser les stubs de conftest.py.
"""
import json
import os
import subprocess
import sys

import pytest

LAMBDA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda")

SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import lambda_function as lf

class Client:
    def voice(self, query, device_id="", person_id="", locale="", force_exact=False, timeout=6.0):
        if query == "éteins tout":
            return {"reply": "ids " + device_id + " " + person_id + " " + locale, "matched": True}
        return {"reply": "Salon : 21.5 °C & sec", "matched": True}

lf.configure(dict(lf.CONFIG, jeedom_url="https://j.example", jeedom_apikey="abcdefghijklmnopqrstu"), Client())

def envelope(request, apl=True, new=True, attributes=None):
    interfaces = {"Alexa.Presentation.APL": {"runtime": {"maxVersion": "1.6"}}} if apl else {}
    return {
        "version": "1.0",
        "session": {"new": new, "sessionId": "s", "application": {"applicationId": "a"},
                    "attributes": attributes or {}, "user": {"userId": "u"}},
        "context": {"System": {"application": {"applicationId": "a"}, "user": {"userId": "u"},
                               "device": {"deviceId": "d", "supportedInterfaces": interfaces},
                               "apiEndpoint": "https://api.eu.amazonalexa.com"}},
        "request": request,
    }

def intent(text):
    return {"type": "IntentRequest", "requestId": "r", "timestamp": "2026-10-30T10:00:00Z", "locale": "fr-FR",
            "intent": {"name": "JeedomQueryIntent", "confirmationStatus": "NONE",
                       "slots": {"query": {"name": "query", "value": text, "confirmationStatus": "NONE"}}}}

out = {}
out["launch"] = lf.lambda_handler(envelope({"type": "LaunchRequest", "requestId": "r", "timestamp": "2026-10-30T10:00:00Z", "locale": "fr-FR"}), None)
out["query"] = lf.lambda_handler(envelope(intent("température salon"), new=False, attributes={"conversation": True}), None)
out["dashboard"] = lf.lambda_handler(envelope(intent("ouvre jeedom")), None)
env = envelope(intent("éteins tout"))
env["context"]["System"]["person"] = {"personId": "amzn1.ask.person.P"}
env["context"]["System"]["device"]["deviceId"] = "amzn1.ask.device.D"
out["voice"] = lf.lambda_handler(env, None)
print(json.dumps(out))
"""


def run_real():
    probe = subprocess.run([sys.executable, "-c", "import ask_sdk_core"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("ask-sdk-core non installé")
    done = subprocess.run([sys.executable, "-c", SCRIPT, LAMBDA_DIR], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_real_sdk_responses():
    out = run_real()

    launch = out["launch"]["response"]
    assert launch["shouldEndSession"] is False
    assert launch["directives"][0]["type"] == "Alexa.Presentation.APL.RenderDocument"
    assert launch["directives"][0]["datasources"]["jeedom"]["url"] == "https://j.example/index.php?v=m"
    assert out["launch"]["sessionAttributes"]["conversation"] is True

    query = out["query"]["response"]
    assert query["outputSpeech"]["ssml"] == "<speak>Salon : 21,5 °C &amp; sec.</speak>"
    assert query["shouldEndSession"] is False

    dashboard = out["dashboard"]["response"]["directives"]
    assert [d["type"] for d in dashboard] == [
        "Alexa.Presentation.APL.RenderDocument",
        "Alexa.Presentation.APL.ExecuteCommands",
    ]
    assert dashboard[1]["commands"][0]["type"] == "OpenURL"
    assert dashboard[1]["commands"][0]["source"] == "https://j.example/index.php?v=m"


def test_real_sdk_voice_router_ids():
    out = run_real()
    speech = out["voice"]["response"]["outputSpeech"]["ssml"]
    assert speech == "<speak>ids amzn1.ask.device.D amzn1.ask.person.P fr-FR.</speak>"
