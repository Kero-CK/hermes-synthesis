"""Le journal extract doit porter le modèle réellement servi (model_served),
y compris sur les entrées de retry, et rien en mode mock.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"
SPEC = importlib.util.spec_from_file_location("sysrev_extract_served", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


EXACT_SENTENCE = "The measured gain was 12% over two years."
FULLTEXT = "# Paper\n\n## Results\n" + EXACT_SENTENCE + " Closing sentence.\n"


def make_review(root: Path) -> str:
    (root / "sources").mkdir(parents=True)
    doi = "10.1234/served-extract"
    (root / "sources" / f"{doi.replace('/', '_')}.md").write_text(FULLTEXT, encoding="utf-8")
    (root / "protocol.md").write_text(
        "# Protocol\n\n## Codebook d'extraction\n- **gain** : gain mesuré\n## Fin\n",
        encoding="utf-8",
    )
    (root / "candidates.csv").write_text(
        f"title,doi,source_id,year,abstract,oa_url\nPaper,{doi},,2024,,\n",
        encoding="utf-8",
    )
    (root / "decisions.jsonl").write_text(
        json.dumps({"doc": doi, "stage": "fulltext", "decision": "retrieved"}) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"id": "served-extract", "stage": "fulltext_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


def journal(root: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ModelServedTests(unittest.TestCase):
    def test_served_model_is_journaled_on_extracted_cells(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            with patch.object(
                extract, "_call_llm_extract",
                return_value=(
                    {"valeur": "12%", "citation": EXACT_SENTENCE, "section": "Results"},
                    "served-model-e",
                ),
            ):
                extract.main(rid, use_mock=False)
            cells = [e for e in journal(root) if e.get("stage") == "extract"]
            self.assertEqual(len(cells), 1)
            self.assertEqual(cells[0]["decision"], "extracted")
            self.assertEqual(cells[0]["model_served"], "served-model-e")

    def test_retry_entries_carry_the_retry_served_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            with patch.object(
                extract, "llm_extract",
                return_value={"valeur": "12%", "citation": "a paraphrase",
                              "section": "Results", "model_served": "served-pass1"},
            ), patch.object(
                extract, "llm_extract_retry",
                return_value={"valeur": "12%",
                              "candidates": [{"citation": EXACT_SENTENCE, "section": "Results"}],
                              "model_served": "served-retry"},
            ):
                extract.main(rid, use_mock=False)
            cells = [e for e in journal(root) if e.get("stage") == "extract"]
            by_decision = {e["decision"]: e for e in cells}
            self.assertEqual(by_decision["citation_retry"]["model_served"], "served-retry")
            self.assertEqual(by_decision["extracted"]["model_served"], "served-retry")

    def test_mock_mode_entries_have_no_model_served_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            extract.main(rid, use_mock=True)
            cells = [e for e in journal(root) if e.get("stage") == "extract"]
            self.assertEqual(len(cells), 1)
            self.assertNotIn("model_served", cells[0])


if __name__ == "__main__":
    unittest.main()
