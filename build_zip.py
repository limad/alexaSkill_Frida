# -*- coding: utf-8 -*-
"""Construit lambda.zip pour le bouton « Import Code » de l'onglet Code (console Alexa).

Amazon attend un dossier `lambda/` à la racine du zip. Si `lambda/config.local.py`
existe (ignoré par git), il est placé dans le zip à la place de `config.py` :
vos vrais réglages ne passent jamais par le dépôt.

    python build_zip.py [chemin/du/zip]
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
LAMBDA_DIR = os.path.join(ROOT, "lambda")
LOCAL_CONFIG = "config.local.py"
SKIPPED_DIRS = ("__pycache__",)


def files_to_pack():
    """(chemin sur disque, chemin dans le zip) de chaque fichier de lambda/."""
    local = os.path.join(LAMBDA_DIR, LOCAL_CONFIG)
    for folder, dirs, files in os.walk(LAMBDA_DIR):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        for name in sorted(files):
            if name.endswith(".pyc") or name == LOCAL_CONFIG:
                continue
            path = os.path.join(folder, name)
            if name == "config.py" and folder == LAMBDA_DIR and os.path.exists(local):
                path = local
            yield path, "lambda/" + os.path.relpath(os.path.join(folder, name), LAMBDA_DIR).replace(os.sep, "/")


def build(output):
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in files_to_pack():
            archive.write(path, arcname)
    return output


if __name__ == "__main__":
    target = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "lambda.zip"))
    print("Créé : {}".format(target))
