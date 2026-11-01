# -*- coding: utf-8 -*-
import pytest

import helpers


def write(tmp_path, text):
    path = tmp_path / "config.py"
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestConfig:
    def test_defaults_when_file_missing(self, tmp_path):
        cfg = helpers.load_config(str(tmp_path / "absent.py"))
        assert cfg["jeedom_dashboard"] == "index.php?v=m"
        assert cfg["keep_session_open"] is True
        assert cfg["keep_session_open_oneshot"] is False
        assert cfg["debug"] is False
        assert helpers.config_errors(cfg) == ["jeedom_url", "jeedom_apikey"]

    def test_spaces_and_trailing_slash(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, 'JEEDOM_URL = " https://jeedom.example/ "\nJEEDOM_APIKEY= "abcdefghijklmnopq"\n'))
        assert cfg["jeedom_url"] == "https://jeedom.example"
        assert cfg["jeedom_apikey"] == "abcdefghijklmnopq"
        assert helpers.config_errors(cfg) == []

    def test_booleans_python_or_text(self, tmp_path):
        # Saisie à la main : False, "False", "false" ou 0 valent faux.
        cfg = helpers.load_config(write(tmp_path, 'DEBUG = False\nVERIFY_SSL = "false"\nKEEP_SESSION_OPEN = 0\n'))
        assert cfg["debug"] is False
        assert cfg["verify_ssl"] is False
        assert cfg["keep_session_open"] is False

    def test_timeout_is_capped_below_alexa_limit(self, tmp_path):
        assert helpers.load_config(write(tmp_path, "JEEDOM_TIMEOUT = 30"))["jeedom_timeout"] == helpers.MAX_TIMEOUT
        assert helpers.load_config(write(tmp_path, "JEEDOM_TIMEOUT = 0"))["jeedom_timeout"] == 1.0
        assert helpers.load_config(write(tmp_path, 'JEEDOM_TIMEOUT = "4,5"'))["jeedom_timeout"] == 4.5
        assert helpers.load_config(write(tmp_path, 'JEEDOM_TIMEOUT = "abc"'))["jeedom_timeout"] == helpers.DEFAULT_TIMEOUT

    def test_placeholders_are_reported(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, 'JEEDOM_URL = "https://VOTRE-URL-JEEDOM-EXTERNE"\nJEEDOM_APIKEY = "VOTRE-CLE-API-JEEDOM"\n'))
        assert helpers.config_errors(cfg) == ["jeedom_url", "jeedom_apikey"]

    def test_url_without_scheme_is_reported(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, 'JEEDOM_URL = "jeedom.example"\nJEEDOM_APIKEY = "abcdefghijklmnopq"\n'))
        assert helpers.config_errors(cfg) == ["jeedom_url"]

    def test_comments_ignored(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, '# JEEDOM_DASHBOARD = "x"\nJEEDOM_DASHBOARD = "salon"\n'))
        assert cfg["jeedom_dashboard"] == "salon"

    def test_typo_gives_not_configured_instead_of_crash(self, tmp_path):
        # Guillemet oublié : le skill doit répondre « non configuré », pas planter à l'import.
        cfg = helpers.load_config(write(tmp_path, 'JEEDOM_URL = "https://jeedom.example\nJEEDOM_APIKEY = "abcdefghijklmnopq"\n'))
        assert helpers.config_errors(cfg) == ["jeedom_url", "jeedom_apikey"]

    def test_lowercase_names_ignored(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, 'jeedom_url = "https://j.example"\n'))
        assert cfg["jeedom_url"] == ""


class TestLocale:
    def test_exact_locale(self):
        assert helpers.load_locale("fr-FR")["alexa_speak_question"] == "Autre chose ?"

    def test_same_language_fallback(self):
        assert helpers.load_locale("fr-BE")["alexa_speak_question"] == "Autre chose ?"

    def test_unknown_language_falls_back_to_english(self):
        assert helpers.load_locale("ja-JP")["alexa_speak_question"] == "Anything else?"

    def test_none_locale(self):
        assert helpers.load_locale(None)["alexa_speak_question"] == "Anything else?"


class TestKeywords:
    def test_whole_word_only(self):
        assert helpers.matches_keyword("ouvre jeedom", "ouvre jeedom")
        assert not helpers.matches_keyword("ouvre jeedomette", "ouvre jeedom")

    def test_accents_and_case_ignored(self):
        assert helpers.matches_keyword("Ouvre le Tableau de Bord", "ouvre le tableau de bord")
        assert helpers.matches_keyword("ÖFFNE das Dashboard", "öffne das dashboard")
        assert helpers.matches_keyword("c\u2019est tout", "c'est tout")

    def test_any_keyword_of_the_list(self):
        assert helpers.matches_keyword("affiche jeedom", "ouvre jeedom; affiche jeedom")
        assert not helpers.matches_keyword("affiche", "ouvre jeedom; affiche jeedom")

    def test_empty_list(self):
        assert not helpers.matches_keyword("non", "")
        assert not helpers.matches_keyword("non", None)
        assert not helpers.matches_keyword("non", " ; ")

    def test_exit_only_for_short_sentences(self):
        words = "non;rien;c'est tout;merci"
        assert helpers.is_exit_request("non merci", words)
        assert helpers.is_exit_request("c'est tout", words)
        assert not helpers.is_exit_request("allume la lumière du salon merci", words)
        assert not helpers.is_exit_request("nonante", words)

    def test_split_list(self):
        assert helpers.split_list(" a; b ;;c ") == ["a", "b", "c"]
        assert helpers.split_list(None) == []


class TestPluginOnlyConfig:
    def test_core_options_ignored(self, tmp_path):
        cfg = helpers.load_config(write(tmp_path, 'JEEDOM_URL = "https://j"\nJEEDOM_APIKEY = "abcdefghijklmnopq"\n'
                                                  'JEEDOM_BACKEND = "core"\nJEEDOM_PROFILE = "x"\nJEEDOM_PROMPT_VARIABLE = "v"\n'))
        assert set(cfg) & {"jeedom_backend", "jeedom_plugin_apikey", "jeedom_profile", "jeedom_prompt_variable"} == set()
        assert helpers.config_errors(cfg) == []


class TestParseChoice:
    FR = helpers.load_locale("fr-FR")

    def choice(self, text, count):
        return helpers.parse_choice(text, count, self.FR["choice_numbers"], self.FR["choice_yes"])

    @pytest.mark.parametrize("text, count, expected", [
        ("oui", 1, 0), ("d'accord", 1, 0), ("un", 1, 0),
        ("2", 3, 1), ("le deuxième", 3, 1), ("deux", 3, 1), ("la troisième", 3, 2), ("numéro 1", 2, 0),
        ("oui", 3, None), ("4", 3, None), ("cinq", 3, None),
        ("allume un peu le salon", 1, None), ("éteins la cuisine", 2, None),
    ])
    def test_french(self, text, count, expected):
        assert self.choice(text, count) == expected

    def test_english(self):
        en = helpers.load_locale("en-US")
        assert helpers.parse_choice("the second one", 2, en["choice_numbers"], en["choice_yes"]) == 1
        assert helpers.parse_choice("yes", 1, en["choice_numbers"], en["choice_yes"]) == 0


class TestCleanForSpeech:
    def test_none_and_empty(self):
        assert helpers.clean_for_speech(None) == ""
        assert helpers.clean_for_speech("") == ""

    def test_negative_numbers_and_percent_kept(self):
        # L'original supprimait « - » et « % » : -5 °C devenait 5 °C.
        assert helpers.clean_for_speech("Il fait -5 °C, humidité 80 %", "fr-FR") == "Il fait -5 °C, humidité 80 %."

    def test_decimal_comma_for_french(self):
        assert helpers.clean_for_speech("Salon : 21.5 °C", "fr-FR") == "Salon : 21,5 °C."

    def test_decimal_point_kept_for_english(self):
        assert helpers.clean_for_speech("Living room 21.5 °C", "en-US") == "Living room 21.5 °C."

    def test_ip_and_versions_untouched(self):
        assert "192.168.1.10" in helpers.clean_for_speech("IP 192.168.1.10", "fr-FR")
        assert "4.5.2" in helpers.clean_for_speech("Jeedom 4.5.2", "fr-FR")

    def test_html_and_entities(self):
        text = helpers.clean_for_speech("<b>Salon</b> : allumé<br/>Cuisine&nbsp;: éteint", "fr-FR")
        assert text == "Salon : allumé. Cuisine : éteint."

    def test_markdown_lists_and_emojis(self):
        text = helpers.clean_for_speech("**Lumières** 💡\n- salon_tv : on\n- cuisine : off 👍", "fr-FR")
        assert text == "Lumières. salon tv : on. cuisine : off."

    def test_existing_punctuation_not_doubled(self):
        assert helpers.clean_for_speech("C'est fait.\nAutre chose ?", "fr-FR") == "C'est fait. Autre chose ?"

    def test_long_text_cut_on_sentence(self):
        text = helpers.clean_for_speech("Phrase un. " * 1000, "fr-FR", max_length=50)
        assert len(text) <= 50
        assert text.endswith(".")

    def test_ssml_escaping(self):
        assert helpers.ssml_safe("Tom & Jerry <3") == "Tom &amp; Jerry &lt;3"
        assert helpers.ssml_safe(None) == ""


class TestDashboardUrl:
    @pytest.mark.parametrize("dashboard, expected", [
        ("", "https://j.example/index.php?v=m"),
        ("index.php?v=d&p=plan&plan_id=2&fullscreen=1", "https://j.example/index.php?v=d&p=plan&plan_id=2&fullscreen=1"),
        ("/index.php?v=m", "https://j.example/index.php?v=m"),
        ("https://autre.example/design", "https://autre.example/design"),
    ])
    def test_build(self, dashboard, expected):
        assert helpers.dashboard_url("https://j.example/", dashboard) == expected
