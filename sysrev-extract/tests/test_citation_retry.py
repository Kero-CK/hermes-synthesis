"""Tests de la passe de retry sur CITATION REJETÉE.

Contrat : le retry peut sauver une cellule UNIQUEMENT en produisant une
citation vérifiable mot à mot (citation_is_verifiable inchangée). Tout le
reste — paraphrase persistante, NON TROUVÉ, API muette — retombe sur le
comportement historique CITATION REJETÉE.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"
SPEC = importlib.util.spec_from_file_location("sysrev_extract_retry", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


EXACT_SENTENCE = "The measured productivity gain was 12% over two years."
FULLTEXT = (
    "# Paper\n\n## Results\n"
    "Some context sentence here. "
    + EXACT_SENTENCE
    + " Another closing sentence.\n"
)


def make_review(root: Path) -> tuple[str, str]:
    (root / "sources").mkdir(parents=True)
    doi = "10.1234/retry-case"
    safe = extract.safe_document_filename(doi, "doi")
    (root / "sources" / f"{safe}.md").write_text(FULLTEXT, encoding="utf-8")
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
        json.dumps({"id": "retry", "stage": "fulltext_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/"), doi


def paraphrased_first_pass(_text, _name, _desc, _doc):
    return {"valeur": "12% sur 2 ans", "citation": "productivity increased by twelve percent",
            "section": "Results"}


def run_extract(root: Path, rid: str, retry_result):
    with patch.object(extract, "llm_extract", side_effect=paraphrased_first_pass), \
            patch.object(extract, "llm_extract_retry", return_value=retry_result):
        extract.main(rid, use_mock=False)
    with (root / "extraction.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    journal = [
        json.loads(line)
        for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return rows, journal, manifest


class CitationRetryTests(unittest.TestCase):
    def test_retry_with_exact_citation_recovers_the_cell(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            rows, journal, manifest = run_extract(root, rid, {
                "valeur": "12% sur 2 ans",
                "candidates": [
                    {"citation": "still a paraphrase", "section": "Results"},
                    {"citation": EXACT_SENTENCE, "section": "Results"},
                ],
            })
            self.assertEqual(rows[0]["valeur"], "12% sur 2 ans")
            self.assertEqual(rows[0]["citation"], EXACT_SENTENCE)
            stages = [(e.get("decision")) for e in journal if e.get("stage") == "extract"]
            self.assertIn("citation_retry", stages)
            self.assertIn("extracted", stages)
            self.assertNotIn("rejected_citation", stages)
            self.assertEqual(manifest["extraction_citation_retries"], 1)
            self.assertEqual(manifest["extraction_retry_recovered"], 1)
            self.assertEqual(manifest["extraction_rejected_citations"], 0)

    def test_retry_with_only_paraphrases_still_rejects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            rows, journal, manifest = run_extract(root, rid, {
                "valeur": "12% sur 2 ans",
                "candidates": [
                    {"citation": "a paraphrase again", "section": "Results"},
                    {"citation": "another rewording", "section": "Results"},
                ],
            })
            self.assertEqual(rows[0]["valeur"], "CITATION REJETÉE")
            self.assertEqual(rows[0]["citation"], "")
            stages = [(e.get("decision")) for e in journal if e.get("stage") == "extract"]
            self.assertIn("citation_retry", stages)
            self.assertIn("rejected_citation", stages)
            self.assertEqual(manifest["extraction_citation_retries"], 1)
            self.assertEqual(manifest["extraction_retry_recovered"], 0)
            self.assertEqual(manifest["extraction_rejected_citations"], 1)

    def test_retry_saying_not_found_cannot_rescue_the_cell(self):
        # Un retry qui répond NON TROUVÉ avec une citation pourtant exacte
        # ne doit PAS produire de valeur : la cellule reste rejetée.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            rows, _, manifest = run_extract(root, rid, {
                "valeur": "NON TROUVÉ",
                "candidates": [{"citation": EXACT_SENTENCE, "section": "Results"}],
            })
            self.assertEqual(rows[0]["valeur"], "CITATION REJETÉE")
            self.assertEqual(manifest["extraction_rejected_citations"], 1)
            self.assertEqual(manifest["extraction_retry_recovered"], 0)

    def test_retry_api_failure_falls_back_without_retry_journal_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            rows, journal, manifest = run_extract(root, rid, None)
            self.assertEqual(rows[0]["valeur"], "CITATION REJETÉE")
            stages = [(e.get("decision")) for e in journal if e.get("stage") == "extract"]
            self.assertNotIn("citation_retry", stages)
            self.assertIn("rejected_citation", stages)
            self.assertEqual(manifest["extraction_citation_retries"], 0)

    def test_mock_mode_behaviour_is_unchanged(self):
        # En mode mock, aucune tentative de retry : une citation invérifiable
        # est rejetée exactement comme avant.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            with patch.object(extract, "mock_extract", side_effect=paraphrased_first_pass), \
                    patch.object(extract, "llm_extract_retry",
                                 side_effect=AssertionError("retry LLM interdit en mock")):
                extract.main(rid, use_mock=True)
            with (root / "extraction.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["valeur"], "CITATION REJETÉE")
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["extraction_citation_retries"], 0)


if __name__ == "__main__":
    unittest.main()
