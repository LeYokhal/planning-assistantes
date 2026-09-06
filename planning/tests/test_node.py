"""Pont vers les tests Node du moteur : `node --test`, sans npm.

Sur le poste, Node est présent et les tests JS tournent dans la même commande
que `pytest`. Là où Node manque (image Docker `python:3.14-slim`), le test est
sauté et le dit : les tests JS n'ont alors PAS tourné.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parent.parent.parent
MOTIF = "planning/tests_js/**/*.test.js"


def test_moteur_js():
    node = shutil.which("node")
    if not node:
        pytest.skip("tests JS non exécutés : node absent")

    resultat = subprocess.run(
        [node, "--test", MOTIF],
        cwd=DEPOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert resultat.returncode == 0, (
        "tests JS en échec\n--- stdout ---\n" + resultat.stdout + "\n--- stderr ---\n" + resultat.stderr
    )
    assert "# fail 0" in resultat.stdout or "fail 0" in resultat.stdout
