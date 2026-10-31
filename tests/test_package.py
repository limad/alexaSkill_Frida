# -*- coding: utf-8 -*-
"""Cohérence du paquet : langues, modèles d'interaction, APL, config d'exemple."""
import glob
import json
import os

import helpers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = sorted(glob.glob(os.path.join(ROOT, "skill-package/interactionModels/custom/*.json")))
LANGS = sorted(glob.glob(os.path.join(ROOT, "lambda/locale/*.lang")))


def locales(paths):
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in paths)


def test_thirteen_languages_everywhere():
    skill = json.load(open(os.path.join(ROOT, "skill-package/skill.json"), encoding="utf-8"))
    published = sorted(skill["manifest"]["publishingInformation"]["locales"])
    assert len(MODELS) == 13
    assert locales(MODELS) == locales(LANGS) == published


def test_all_lang_files_have_the_same_keys():
    reference = set(helpers.parse_kv_file(os.path.join(ROOT, "lambda/locale/en-US.lang")))
    for path in LANGS:
        texts = helpers.parse_kv_file(path)
        assert set(texts) == reference, path
        assert all(texts.values()), path
        assert helpers.split_list(texts["alexa_speak_exit"]), path


def test_texts_used_by_code_exist():
    source = open(os.path.join(ROOT, "lambda/lambda_function.py"), encoding="utf-8").read()
    keys = set(helpers.parse_kv_file(os.path.join(ROOT, "lambda/locale/en-US.lang")))
    import re
    used = set(re.findall(r'\["((?:alexa_speak|echo_screen|keywords)_[a-z_]+)"\]', source))
    used |= set(re.findall(r'"(alexa_speak_[a-z_]+)"', source))
    assert used and used <= keys, used - keys


def test_interaction_models():
    for path in MODELS:
        model = json.load(open(path, encoding="utf-8"))["interactionModel"]["languageModel"]
        assert "frida" in model["invocationName"], path
        assert model["invocationName"] == model["invocationName"].lower()
        intents = {i["name"]: i for i in model["intents"]}
        query = intents["JeedomQueryIntent"]
        assert query["samples"] == ["{query}"]
        assert query["slots"] == [{"name": "query", "type": "AMAZON.Person"}]
        for builtin in ("AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.HelpIntent",
                        "AMAZON.FallbackIntent", "AMAZON.NavigateHomeIntent",
                        "AMAZON.YesIntent", "AMAZON.NoIntent"):
            assert builtin in intents, (path, builtin)


def test_apl_documents_are_valid_json():
    for name in ("apl_dashboard.json", "apl_empty.json"):
        doc = json.load(open(os.path.join(ROOT, "lambda", name), encoding="utf-8"))
        assert doc["type"] == "APL"


def test_viewports_declared_for_screens():
    skill = json.load(open(os.path.join(ROOT, "skill-package/skill.json"), encoding="utf-8"))
    interfaces = skill["manifest"]["apis"]["custom"]["interfaces"]
    apl = [i for i in interfaces if i["type"] == "ALEXA_PRESENTATION_APL"][0]
    modes = {(v["mode"], v["shape"]) for v in apl["supportedViewports"]}
    assert ("HUB", "ROUND") in modes and ("HUB", "RECTANGLE") in modes and ("TV", "RECTANGLE") in modes


def test_example_config_has_no_real_secret():
    cfg = helpers.load_config(os.path.join(ROOT, "lambda/config.cfg"))
    assert helpers.config_errors(cfg) == ["jeedom_url", "jeedom_apikey"]
    assert cfg["debug"] is False
    assert "jeedom_backend" not in cfg and "jeedom_prompt_variable" not in cfg


def test_build_zip(tmp_path, monkeypatch):
    import sys
    import zipfile
    sys.path.insert(0, ROOT)
    import build_zip

    lambda_dir = tmp_path / "lambda"
    (lambda_dir / "locale").mkdir(parents=True)
    (lambda_dir / "__pycache__").mkdir()
    (lambda_dir / "lambda_function.py").write_text("x", encoding="utf-8")
    (lambda_dir / "config.cfg").write_text("jeedom_apikey=VOTRE-CLE", encoding="utf-8")
    (lambda_dir / "config.local.cfg").write_text("jeedom_apikey=vraie-cle", encoding="utf-8")
    (lambda_dir / "locale" / "fr-FR.lang").write_text("a=b", encoding="utf-8")
    (lambda_dir / "__pycache__" / "x.pyc").write_bytes(b"")
    monkeypatch.setattr(build_zip, "LAMBDA_DIR", str(lambda_dir))

    with zipfile.ZipFile(build_zip.build(str(tmp_path / "out.zip"))) as archive:
        names = sorted(archive.namelist())
        assert names == ["lambda/config.cfg", "lambda/lambda_function.py", "lambda/locale/fr-FR.lang"]
        assert archive.read("lambda/config.cfg") == b"jeedom_apikey=vraie-cle"
