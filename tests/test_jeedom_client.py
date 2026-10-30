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

    def post(self, url, json=None, timeout=None, verify=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout, "verify": verify})
        if self.exc:
            raise self.exc
        return self.response


def client(response=None, exc=None, **kwargs):
    session = FakeSession(response, exc)
    return JeedomClient("https://j.example/", APIKEY, session=session, **kwargs), session


def ok(result):
    return FakeResponse(json_data={"jsonrpc": "2.0", "id": 1, "result": result})


class TestAsk:
    def test_request_shape(self):
        c, s = client(ok({"reply": "C'est fait"}), profile="Salon", verify_ssl=False)
        assert c.ask("allume le salon", timeout=3.0) == "C'est fait"
        call = s.calls[0]
        assert call["url"] == "https://j.example/core/api/jeeApi.php"
        assert call["json"]["method"] == "interact::tryToReply"
        assert call["json"]["params"] == {"query": "allume le salon", "profile": "Salon", "apikey": APIKEY}
        assert call["timeout"] == (1.5, 1.5)  # connexion + lecture = budget
        assert call["verify"] is False

    def test_no_profile_param_when_empty(self):
        c, s = client(ok({"reply": "ok"}))
        c.ask("test")
        assert "profile" not in s.calls[0]["json"]["params"]

    @pytest.mark.parametrize("result, expected", [
        ({"reply": None}, ""), ({}, ""), ("texte", "texte"), (True, ""), ({"reply": 21.5}, "21.5"),
    ])
    def test_result_variants(self, result, expected):
        c, _ = client(ok(result))
        assert c.ask("x") == expected


class TestErrors:
    def kind_of(self, **kwargs):
        c, _ = client(**kwargs)
        with pytest.raises(JeedomError) as info:
            c.ask("x")
        assert APIKEY not in str(info.value)
        return info.value.kind

    def test_timeout(self):
        assert self.kind_of(exc=requests.exceptions.ReadTimeout()) == "timeout"

    def test_timeout_split_between_connect_and_read(self):
        c, s = client(ok({"reply": "ok"}))
        c.ask("x", timeout=6.5)
        assert s.calls[0]["timeout"] == (2.0, 4.5)

    def test_connect_timeout_means_unreachable(self):
        assert self.kind_of(exc=requests.exceptions.ConnectTimeout()) == "unreachable"

    def test_connection_error(self):
        assert self.kind_of(exc=requests.exceptions.ConnectionError()) == "unreachable"

    def test_ssl_error(self):
        assert self.kind_of(exc=requests.exceptions.SSLError()) == "unreachable"

    @pytest.mark.parametrize("code", [-32001, -32002, -32701])
    def test_jsonrpc_auth_codes(self, code):
        resp = FakeResponse(json_data={"jsonrpc": "2.0", "error": {"code": code, "message": "refusé"}})
        assert self.kind_of(response=resp) == "auth"

    def test_jsonrpc_other_error(self):
        resp = FakeResponse(json_data={"jsonrpc": "2.0", "error": {"code": -32500, "message": "Aucune méthode"}})
        assert self.kind_of(response=resp) == "error"

    def test_http_403(self):
        assert self.kind_of(response=FakeResponse(status=403, text="<html>")) == "auth"

    def test_http_500(self):
        assert self.kind_of(response=FakeResponse(status=500, text="<html>")) == "error"

    def test_html_instead_of_json(self):
        assert self.kind_of(response=FakeResponse(status=200, text="<html>login</html>")) == "error"

    def test_json_without_result(self):
        assert self.kind_of(response=FakeResponse(json_data={"jsonrpc": "2.0"})) == "error"


class TestVariables:
    def test_read_variable(self):
        c, s = client(ok({"id": "3", "type": "scenario", "link_id": "-1", "key": "alexa_prompt", "value": " Bonjour "}))
        assert c.read_variable("alexa_prompt") == "Bonjour"
        params = s.calls[0]["json"]["params"]
        assert s.calls[0]["json"]["method"] == "datastore::byTypeLinkIdKey"
        assert params["type"] == "scenario" and params["linkId"] == -1 and params["key"] == "alexa_prompt"

    @pytest.mark.parametrize("result", [[], False, None, {"value": None}])
    def test_missing_variable(self, result):
        c, _ = client(ok(result))
        assert c.read_variable("absente") == ""

    def test_write_variable(self):
        c, s = client(ok("ok"))
        c.write_variable("alexa_prompt", "")
        call = s.calls[0]["json"]
        assert call["method"] == "datastore::save"
        assert call["params"]["value"] == "" and call["params"]["linkId"] == -1
