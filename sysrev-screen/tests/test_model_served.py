"""Le journal doit porter le modèle réellement servi par l'API (model_served),
à côté de l'alias demandé (model). Cf. experiments/ERRATUM-MODEL-IDENTITY.md.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "screen.py"
SPEC = importlib.util.spec_from_file_location("sysrev_screen_served", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


def make_review(root: Path) -> str:
    (root / "protocol.md").write_text(
        "# Protocole\n\n## Critères d'inclusion\n- Étude empirique pertinente\n"
        "\n## Critères d'exclusion\n- Hors sujet\n\n"
        + "Texte de remplissage pour dépasser le seuil minimal du protocole. " * 3,
        encoding="utf-8",
    )
    (root / "candidates.csv").write_text(
        "title,doi,source_id,year,abstract,oa_url\n"
        "Paper,10.1234/served,,2024,Un abstract,\n",
        encoding="utf-8",
    )
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "prisma.json").write_text("{}", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({
        "id": "served", "stage": "dedup_done", "search_status": "complete",
    }), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class ModelServedTests(unittest.TestCase):
    def test_served_model_is_journaled_next_to_requested_alias(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            with patch.object(
                screen, "_call_llm_api",
                return_value=({"score": 0.9, "reason": "ok"}, "served-model-x"),
            ):
                screen.main(rid, use_mock=False)
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(entries), 1)
            self.assertIn("model", entries[0])
            self.assertEqual(entries[0]["model_served"], "served-model-x")

    def test_mock_mode_entries_have_no_model_served_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            screen.main(rid, use_mock=True)
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(entries), 1)
            self.assertNotIn("model_served", entries[0])


if __name__ == "__main__":
    unittest.main()
