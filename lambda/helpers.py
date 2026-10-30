# -*- coding: utf-8 -*-
"""Fonctions pures du skill : configuration, traductions, texte parlé, mots-clés, URL.

Aucune dépendance à ask-sdk ni à requests : tout est testable directement.
"""
import functools
import glob
import html
import os
import re
import unicodedata
from xml.sax.saxutils import escape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BASE_DIR, "locale")
DEFAULT_LOCALE = "en-US"

TRUE_VALUES = ("1", "true", "yes", "on", "oui")
REQUIRED_KEYS = ("jeedom_url", "jeedom_apikey")
# Valeurs d'exemple de config.cfg : considérées comme « non renseignées ».
PLACEHOLDER_MARKERS = ("YOUR-", "VOTRE-")

# Le délai Alexa est de 8 s au total : on garde une marge pour la Lambda.
MAX_TIMEOUT = 7.5
DEFAULT_TIMEOUT = 6.5

# Langues qui lisent « 21,5 » mieux que « 21.5 ».
DECIMAL_COMMA_LANGS = ("de", "fr", "es", "it", "nl", "pt")
# Symboles gardés même s'ils sont de catégorie « So » (symbole autre).
KEPT_SYMBOLS = "°€$£%"
MAX_SPEECH_LENGTH = 6000


# --------------------------------------------------------------------------
# Fichiers clé=valeur (config.cfg et locale/*.lang)
# --------------------------------------------------------------------------
def parse_kv_file(path):
    """Lit un fichier `clé=valeur` (lignes vides et `#` ignorées, espaces retirés)."""
    values = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def as_bool(value, default=False):
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in TRUE_VALUES


def as_float(value, default):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def load_config(path):
    """Charge config.cfg et renvoie un dict typé. Ne lève jamais d'exception."""
    try:
        raw = parse_kv_file(path)
    except OSError:
        raw = {}
    timeout = as_float(raw.get("jeedom_timeout"), DEFAULT_TIMEOUT)
    return {
        "jeedom_url": raw.get("jeedom_url", "").rstrip("/"),
        "jeedom_apikey": raw.get("jeedom_apikey", ""),
        "jeedom_profile": raw.get("jeedom_profile", ""),
        "jeedom_dashboard": raw.get("jeedom_dashboard", "") or "index.php?v=m",
        "jeedom_prompt_variable": raw.get("jeedom_prompt_variable", ""),
        "jeedom_timeout": min(max(timeout, 1.0), MAX_TIMEOUT),
        "verify_ssl": as_bool(raw.get("verify_ssl"), True),
        "keep_session_open": as_bool(raw.get("keep_session_open"), True),
        "keep_session_open_oneshot": as_bool(raw.get("keep_session_open_oneshot"), False),
        "suppress_greeting": as_bool(raw.get("suppress_greeting"), False),
        "debug": as_bool(raw.get("debug"), False),
    }


def config_errors(config):
    """Liste des clés obligatoires absentes ou laissées à leur valeur d'exemple."""
    missing = []
    for key in REQUIRED_KEYS:
        value = str(config.get(key) or "")
        if not value or any(m in value.upper() for m in PLACEHOLDER_MARKERS):
            missing.append(key)
    url = str(config.get("jeedom_url") or "")
    if "jeedom_url" not in missing and not re.match(r"^https?://", url, re.I):
        missing.append("jeedom_url")
    return missing


_LOCALE_CACHE = {}


def _locale_file(locale):
    path = os.path.join(LOCALE_DIR, "{}.lang".format(locale))
    if os.path.exists(path):
        return path
    # Même langue, autre pays (ex. fr-BE -> fr-FR).
    lang = locale.split("-")[0]
    candidates = sorted(glob.glob(os.path.join(LOCALE_DIR, "{}-*.lang".format(lang))))
    return candidates[0] if candidates else None


def load_locale(locale):
    """Textes de la langue demandée, complétés par l'anglais pour les clés manquantes."""
    locale = locale or DEFAULT_LOCALE
    if locale not in _LOCALE_CACHE:
        texts = parse_kv_file(os.path.join(LOCALE_DIR, DEFAULT_LOCALE + ".lang"))
        path = _locale_file(locale)
        if path:
            texts.update(parse_kv_file(path))
        _LOCALE_CACHE[locale] = texts
    return _LOCALE_CACHE[locale]


# --------------------------------------------------------------------------
# Mots-clés
# --------------------------------------------------------------------------
def normalize(text):
    """Minuscules, sans accents, apostrophes unifiées, espaces simples."""
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def split_list(value):
    """`a;b; c` -> ['a', 'b', 'c'] (éléments vides retirés)."""
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


@functools.lru_cache(maxsize=64)
def _keyword_regex(keywords):
    """Une seule regex par liste `a;b;c` (compilée une fois par conteneur Lambda)."""
    words = sorted({normalize(k) for k in split_list(keywords)} - {""}, key=len, reverse=True)
    if not words:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)")


def matches_keyword(query, keywords):
    """Vrai si un mot-clé de la liste `a;b;c` apparaît comme mot ou expression entière."""
    pattern = _keyword_regex(keywords or "")
    return bool(pattern and pattern.search(normalize(query)))


def is_exit_request(query, keywords, max_words=3):
    """Mot de sortie (« non », « merci »…) dans une phrase courte uniquement."""
    return len(normalize(query).split()) <= max_words and matches_keyword(query, keywords)


# --------------------------------------------------------------------------
# Texte parlé
# --------------------------------------------------------------------------
def _strip_symbols(text):
    kept = []
    for char in text:
        if char in KEPT_SYMBOLS:
            kept.append(char)
            continue
        if char in "‍️":  # liants et sélecteurs d'emoji
            continue
        if unicodedata.category(char) in ("So", "Cs", "Co", "Cn"):
            continue
        kept.append(char)
    return "".join(kept)


def clean_for_speech(text, locale=DEFAULT_LOCALE, max_length=MAX_SPEECH_LENGTH):
    """Rend une réponse Jeedom (HTML, markdown, emojis, retours ligne) lisible à voix haute."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFC", html.unescape(str(text)))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("`", "").replace("*", "").replace("#", " ").replace("_", " ")
    text = re.sub(r"(?m)^\s*(?:[-•]|\d+[.)])\s+", "", text)  # puces de liste
    text = _strip_symbols(text)

    sentences = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" ,")
        if not line:
            continue
        if line[-1] not in ".!?:;,":
            line += "."
        sentences.append(line)
    text = " ".join(sentences)

    if (locale or "").split("-")[0] in DECIMAL_COMMA_LANGS:
        # 21.5 -> 21,5 mais pas 192.168.1.1 ni 1.2.3
        text = re.sub(r"(?<![\d.])(\d+)\.(\d+)(?![.\d])", r"\1,\2", text)

    # Pas d'espace avant « . » et « , » (on garde l'espace français avant « : ? ! ; »).
    text = re.sub(r"\s+([.,])", r"\1", text)
    text = re.sub(r"([.!?])\.+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_length:
        cut = text[:max_length]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[: end + 1] if end > 0 else cut
    return text


def ssml_safe(text):
    """ask-sdk entoure le texte de <speak> : on échappe &, < et >."""
    return escape(str(text or ""))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
def dashboard_url(base_url, dashboard):
    """URL absolue du dashboard : `dashboard` peut être une URL complète ou un chemin Jeedom."""
    target = (dashboard or "").strip() or "index.php?v=m"
    if re.match(r"^https?://", target, re.I):
        return target
    return "{}/{}".format((base_url or "").rstrip("/"), target.lstrip("/"))
