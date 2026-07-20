"""Le journal screen_fulltext doit porter le modèle réellement servi
(model_served) quand l'API le renvoie, et rien en mode mock.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "screen_fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_screen_ft_served", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
screen_fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen_fulltext)


PROTOCOL = (
    "# Protocole\n\n## Critères d'inclusion\n- Étude empirique pertinente\n"
    "\n## Critères d'exclusion\n- Hors sujet\n\n"
    + "Texte de remplissage pour dépasser le seuil minimal du protocole. " * 3
)


def make_review(root: Path) -> str:
    (root / "sources").mkdir(parents=True)
    (root / "protocol.md").write_text(PROTOCOL, encoding="utf-8")
    doi = "10.1234/served-ft"
    (root / "sources" / f"{doi.replace('/', '_')}.md").write_text(
        "# Article\n\n" + "contenu " * 100, encoding="utf-8"
    )
    (root / "decisions.jsonl").write_text(
        json.dumps({"doc": doi, "stage": "fulltext", "decision": "retrieved"}) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"id": "served-ft", "stage": "fulltext_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text("{}", encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class ModelServedTests(unittest.TestCase):
    def test_served_model_is_journaled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            with patch.object(
                screen_fulltext, "_call_llm_api",
                return_value=(
                    {"score": 0.9, "reason": "ok", "criterion": ""},
                    "served-model-ft",
                ),
            ):
                screen_fulltext.main(rid, use_mock=False)
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ft = [e for e in entries if e.get("stage") == "screen_fulltext"]
            self.assertEqual(len(ft), 1)
            self.assertEqual(ft[0]["model_served"], "served-model-ft")

    def test_mock_mode_entries_have_no_model_served_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            screen_fulltext.main(rid, use_mock=True)
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ft = [e for e in entries if e.get("stage") == "screen_fulltext"]
            self.assertEqual(len(ft), 1)
            self.assertNotIn("model_served", ft[0])


if __name__ == "__main__":
    unittest.main()
