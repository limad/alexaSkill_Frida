# -*- coding: utf-8 -*-
"""Client HTTP du routeur vocal du plugin Jeedom alexaapiv2 (`voiceRouter.php` :
interactions, IA via ai_assistant / mcp_jeedom).

Le skill n'appelle que cet endpoint, avec la clé API du plugin alexaapiv2 — jamais
l'API du core ni sa clé. La clé voyage dans l'en-tête Authorization, jamais dans
l'URL, et n'apparaît ni dans les messages d'erreur ni dans les logs.
"""
import requests
from urllib3.util import Timeout

# Part maximale du budget réservée à l'ouverture de connexion (DNS + TCP + TLS).
CONNECT_TIMEOUT = 2.0


class JeedomError(Exception):
    """Erreur d'appel Jeedom. `kind` : timeout, unreachable, auth ou error."""

    def __init__(self, kind, detail=""):
        super(JeedomError, self).__init__("{}: {}".format(kind, detail))
        self.kind = kind
        self.detail = detail


class JeedomClient(object):
    VOICE_ROUTER_PATH = "plugins/alexaapiv2/core/php/voiceRouter.php"

    def __init__(self, url, apikey, verify_ssl=True, session=None):
        base = (url or "").rstrip("/")
        self.voice_endpoint = "{}/{}".format(base, self.VOICE_ROUTER_PATH)
        self._apikey = apikey  # clé API du plugin alexaapiv2
        self.verify_ssl = verify_ssl
        # Session réutilisée entre invocations « chaudes » : connexion TLS gardée.
        self.session = session or requests.Session()

    def _post_json(self, url, payload, timeout, label, headers=None):
        """POST JSON, contrôle HTTP et décodage. Renvoie le dict de la réponse."""
        # Délai total unique (connexion + attente de la réponse) : urllib3 retire le
        # temps réellement passé à se connecter. Un couple (connexion, lecture) fixe
        # perdait la part de connexion même quand celle-ci était immédiate.
        connect = min(CONNECT_TIMEOUT, timeout / 2.0)
        try:
            resp = self.session.post(url, json=payload, headers=headers,
                                     timeout=Timeout(total=timeout, connect=connect),
                                     verify=self.verify_ssl)
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
        headers = {"Authorization": "Bearer {}".format(self._apikey)}
        data = self._post_json(self.voice_endpoint, payload, timeout, "voiceRouter", headers)
        if data.get("error") == "unauthorized":
            raise JeedomError("auth", "voiceRouter unauthorized")
        return data
