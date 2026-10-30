# -*- coding: utf-8 -*-
"""Client JSON-RPC minimal pour l'API du core Jeedom (`core/api/jeeApi.php`).

La clé API voyage dans le corps de la requête et n'apparaît jamais dans les
messages d'erreur ni dans les logs.
"""
import itertools

import requests

# Codes JSON-RPC Jeedom pour « clé refusée » / « droits insuffisants ».
AUTH_ERROR_CODES = (-32001, -32002, -32701)
_ids = itertools.count(1)


class JeedomError(Exception):
    """Erreur d'appel Jeedom. `kind` : timeout, unreachable, auth ou error."""

    def __init__(self, kind, detail=""):
        super(JeedomError, self).__init__("{}: {}".format(kind, detail))
        self.kind = kind
        self.detail = detail


class JeedomClient(object):
    def __init__(self, url, apikey, profile="", verify_ssl=True, session=None):
        self.endpoint = "{}/core/api/jeeApi.php".format((url or "").rstrip("/"))
        self._apikey = apikey
        self.profile = profile
        self.verify_ssl = verify_ssl
        # Session réutilisée entre invocations « chaudes » : connexion TLS gardée.
        self.session = session or requests.Session()

    def call(self, method, params=None, timeout=6.0):
        body = dict(params or {})
        body["apikey"] = self._apikey
        payload = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": body}
        try:
            resp = self.session.post(self.endpoint, json=payload, timeout=timeout, verify=self.verify_ssl)
        except requests.exceptions.Timeout:
            raise JeedomError("timeout", "{} > {:.1f} s".format(method, timeout))
        except requests.exceptions.SSLError:
            raise JeedomError("unreachable", "certificat TLS refusé")
        except requests.exceptions.RequestException as e:
            raise JeedomError("unreachable", type(e).__name__)

        if resp.status_code in (401, 403):
            raise JeedomError("auth", "HTTP {}".format(resp.status_code))
        if resp.status_code >= 400:
            raise JeedomError("error", "HTTP {}".format(resp.status_code))
        try:
            data = resp.json()
        except ValueError:
            raise JeedomError("error", "réponse non JSON (HTTP {})".format(resp.status_code))
        if not isinstance(data, dict):
            raise JeedomError("error", "réponse JSON-RPC invalide")

        error = data.get("error")
        if error:
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message", "") if isinstance(error, dict) else str(error)
            kind = "auth" if code in AUTH_ERROR_CODES else "error"
            raise JeedomError(kind, "{} {}".format(code, str(message)[:200]).strip())
        if "result" not in data:
            raise JeedomError("error", "réponse JSON-RPC sans résultat")
        return data["result"]

    def ask(self, query, timeout=6.0):
        """Envoie la phrase aux interactions Jeedom et renvoie la réponse texte."""
        params = {"query": query}
        if self.profile:
            # Le profil sert de mémoire de contexte côté Jeedom (5 min) et de #profile#.
            params["profile"] = self.profile
        result = self.call("interact::tryToReply", params, timeout)
        if isinstance(result, dict):
            reply = result.get("reply")
            return "" if reply is None else str(reply)
        if isinstance(result, str):
            return result
        return ""

    def read_variable(self, name, timeout=2.0):
        """Valeur d'une variable de scénario ('' si absente)."""
        result = self.call(
            "datastore::byTypeLinkIdKey",
            {"type": "scenario", "linkId": -1, "key": name},
            timeout,
        )
        if isinstance(result, dict):
            value = result.get("value")
            return "" if value is None else str(value).strip()
        return ""

    def write_variable(self, name, value, timeout=2.0):
        self.call(
            "datastore::save",
            {"type": "scenario", "linkId": -1, "key": name, "value": value},
            timeout,
        )
