# -*- coding: utf-8 -*-
import pytest
import requests

from jeedom_client import JeedomClient, JeedomError

APIKEY = "cle-secrete-1234567890"


class FakeResponse(object):
    def __init__(self, status=200, json_data=None, text=""):
        self.status_code = status
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class FakeSession(object):
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None, verify=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout, "verify": verify})
        if self.exc:
            raise self.exc
        return self.response


def client(response=None, exc=None, **kwargs):
    session = FakeSession(response, exc)
    return JeedomClient("https://j.example/", APIKEY, session=session, **kwargs), session


def voice_ok(data=None):
    return FakeResponse(json_data=data or {"reply": "ok", "matched": True})


class TestErrors:
    def kind_of(self, **kwargs):
        c, _ = client(**kwargs)
        with pytest.raises(JeedomError) as info:
            c.voice("x")
        assert APIKEY not in str(info.value)
        return info.value.kind

    def test_timeout(self):
        assert self.kind_of(exc=requests.exceptions.ReadTimeout()) == "timeout"

    def test_connect_timeout_means_unreachable(self):
        assert self.kind_of(exc=requests.exceptions.ConnectTimeout()) == "unreachable"

    def test_connection_error(self):
        assert self.kind_of(exc=requests.exceptions.ConnectionError()) == "unreachable"

    def test_ssl_error(self):
        assert self.kind_of(exc=requests.exceptions.SSLError()) == "unreachable"

    def test_http_403(self):
        assert self.kind_of(response=FakeResponse(status=403, text="<html>")) == "auth"

    def test_http_500(self):
        assert self.kind_of(response=FakeResponse(status=500, text="<html>")) == "error"

    def test_json_not_object(self):
        assert self.kind_of(response=FakeResponse(json_data=["x"])) == "error"


class TestVoiceRouter:
    def test_request_shape(self):
        c, s = client(FakeResponse(json_data={"reply": "C'est fait", "matched": True, "route": "voiceQuery"}),
                      verify_ssl=False)
        result = c.voice("allume la cuisine", device_id="amzn1.ask.device.X", person_id="p1",
                         locale="fr-FR", force_exact=True, timeout=6.5)
        assert result["reply"] == "C'est fait"
        call = s.calls[0]
        assert call["url"] == "https://j.example/plugins/alexaapiv2/core/php/voiceRouter.php"
        assert call["headers"] == {"Authorization": "Bearer " + APIKEY}
        assert call["json"] == {"query": "allume la cuisine", "deviceSerialNumber": "amzn1.ask.device.X",
                                "personId": "p1", "locale": "fr-FR", "forceExact": True}
        assert "apikey" not in call["url"]
        # Délai total : la connexion ne réserve pas sa part quand elle est immédiate.
        assert call["timeout"].total == 6.5
        assert call["timeout"].connect_timeout == 2.0
        assert call["verify"] is False

    @pytest.mark.parametrize("response, kind", [
        (FakeResponse(status=401, json_data={"error": "unauthorized"}), "auth"),
        (FakeResponse(status=200, json_data={"reply": "", "error": "unauthorized"}), "auth"),
        (FakeResponse(status=404, text="Not Found"), "error"),
        (FakeResponse(status=200, text="<html>"), "error"),
    ])
    def test_errors(self, response, kind):
        c, _ = client(response)
        with pytest.raises(JeedomError) as info:
            c.voice("x")
        assert info.value.kind == kind
        assert APIKEY not in str(info.value)


def test_only_plugin_endpoint():
    """Le skill n'a aucun moyen d'appeler l'API du core."""
    c, _ = client(voice_ok())
    assert not hasattr(c, "call") and not hasattr(c, "ask")
    assert not hasattr(c, "read_variable") and not hasattr(c, "write_variable")


def test_short_budget_halves_connect():
    c, s = client(voice_ok())
    c.voice("x", timeout=1.0)
    assert s.calls[0]["timeout"].total == 1.0
    assert s.calls[0]["timeout"].connect_timeout == 0.5
