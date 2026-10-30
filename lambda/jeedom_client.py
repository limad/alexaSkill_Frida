# -*- coding: utf-8 -*-
"""Client HTTP Jeedom : API JSON-RPC du core (`core/api/jeeApi.php`) et routeur
vocal du plugin alexaapiv2 (`voiceRouter.php`, IA via ai_assistant / mcp_jeedom).

La clé API voyage dans le corps (core) ou l'en-tête Authorization (plugin), jamais
dans l'URL, et n'apparaît jamais dans les messages d'erreur ni dans les logs.
"""
import itertools

import requests

# Codes JSON-RPC Jeedom pour « clé refusée » / « droits insuffisants ».
AUTH_ERROR_CODES = (-32001, -32002, -32701)
# Part maximale du budget réservée à l'ouverture de connexion (DNS + TCP + TLS).
CONNECT_TIMEOUT = 2.0
_ids = itertools.count(1)


class JeedomError(Exception):
    """Erreur d'appel Jeedom. `kind` : timeout, unreachable, auth ou error."""

    def __init__(self, kind, detail=""):
        super(JeedomError, self).__init__("{}: {}".format(kind, detail))
        self.kind = kind
        self.detail = detail


class JeedomClient(object):
    VOICE_ROUTER_PATH = "plugins/alexaapiv2/core/php/voiceRouter.php"

    def __init__(self, url, apikey, profile="", verify_ssl=True, session=None, plugin_apikey=""):
        base = (url or "").rstrip("/")
        self.endpoint = "{}/core/api/jeeApi.php".format(base)
        self.voice_endpoint = "{}/{}".format(base, self.VOICE_ROUTER_PATH)
        self._apikey = apikey
        # voiceRouter refuse la clé du core : clé du plugin alexaapiv2 ou clé utilisateur.
        self._plugin_apikey = plugin_apikey or apikey
        self.profile = profile
        self.verify_ssl = verify_ssl
        # Session réutilisée entre invocations « chaudes » : connexion TLS gardée.
        self.session = session or requests.Session()

    def _post_json(self, url, payload, timeout, label, headers=None):
        """POST JSON, contrôle HTTP et décodage. Renvoie le dict de la réponse."""
        # requests applique le délai à la connexion PUIS à la lecture : on partage le
        # budget entre les deux pour que le total reste sous `timeout`.
        connect = min(CONNECT_TIMEOUT, timeout / 2.0)
        read = max(timeout - connect, 0.3)
        try:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=(connect, read), verify=self.verify_ssl)
        except requests.exceptions.ConnectTimeout:
            raise JeedomError("unreachable", "connexion > {:.1f} s".format(connect))
        except requests.exceptions.Timeout:
            raise JeedomError("timeout", "{} > {:.1f} s".format(label, timeout))
        except requests.exceptions.SSLError:
            raise JeedomError("unreachable", "certificat TLS refusé")
        except requests.exceptions.RequestException as e:
            raise JeedomError("unreachable", type(e).__name__)

        if resp.status_code in (401, 403):
            raise JeedomError("auth", "{} HTTP {}".format(label, resp.status_code))
        if resp.status_code >= 400:
            raise JeedomError("error", "{} HTTP {}".format(label, resp.status_code))
        try:
            data = resp.json()
        except ValueError:
            raise JeedomError("error", "{} : réponse non JSON (HTTP {})".format(label, resp.status_code))
        if not isinstance(data, dict):
            raise JeedomError("error", "{} : réponse JSON invalide".format(label))
        return data

    def call(self, method, params=None, timeout=6.0):
        body = dict(params or {})
        body["apikey"] = self._apikey
        payload = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": body}
        data = self._post_json(self.endpoint, payload, timeout, method)
        error = data.get("error")
        if error:
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message", "") if isinstance(error, dict) else str(error)
            kind = "auth" if code in AUTH_ERROR_CODES else "error"
            raise JeedomError(kind, "{} {}".format(code, str(message)[:200]).strip())
        if "result" not in data:
            raise JeedomError("error", "réponse JSON-RPC sans résultat")
        return data["result"]

    def voice(self, query, device_id="", person_id="", locale="", force_exact=False, timeout=6.0):
        """Routeur vocal alexaapiv2 : interactions, LLM (voiceQuery) ou MCP en asynchrone.

        Renvoie le dict du plugin : reply, matched, route, et pour un choix à faire
        ambiguous=True + options=[phrases à renvoyer avec force_exact].
        """
        payload = {
            "query": query,
            "deviceSerialNumber": device_id,  # amzn1.ask.device.… : le plugin le relie à l'Echo
            "personId": person_id,
            "locale": locale,
            "forceExact": bool(force_exact),
        }
        headers = {"Authorization": "Bearer {}".format(self._plugin_apikey)}
        data = self._post_json(self.voice_endpoint, payload, timeout, "voiceRouter", headers)
        if data.get("error") == "unauthorized":
            raise JeedomError("auth", "voiceRouter unauthorized")
        return data

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
