from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report.py"
SPEC = importlib.util.spec_from_file_location("sysrev_report_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def make_report_review(root: Path, *, codebook: str = "- **variable** : description\n",
                       fulltext_retrieved: int = 0, included: int = 0,
                       extraction_rows: list[dict] | None = None,
                       extraction_articles: int | None = None) -> str:
    protocol = f"# Protocol\n\n## Codebook d'extraction\n{codebook}"
    (root / "protocol.md").write_text(protocol, encoding="utf-8")
    rows = extraction_rows or []
    fields = ["doi", "source_id", "oa_url", "doc", "identity_type",
              "variable", "valeur", "citation", "section"]
    with (root / "extraction.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (root / "prisma.json").write_text(json.dumps({
        "identified": included, "after_dedup": included, "screened": included,
        "included": included, "fulltext_assessed": fulltext_retrieved,
        "fulltext_retrieved": fulltext_retrieved,
        "fulltext_not_retrieved": 0,
    }), encoding="utf-8")
    manifest = {"id": "report", "stage": "extract_done", "review_mode": "scoping"}
    if extraction_articles is not None:
        manifest["extraction_articles"] = extraction_articles
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class ReportIdentityTests(unittest.TestCase):
    def test_distinct_no_doi_decisions_resolve_independently(self):
        entries = [
            {"doc": "W1", "stage": "screen_title_abstract", "decision": "include"},
            {"doc": "W2", "stage": "screen_title_abstract", "decision": "include"},
        ]
        decisions, unknown = report.resolve_screening_decisions(entries)
        self.assertEqual([entry["doc"] for entry in decisions], ["W1", "W2"])
        self.assertEqual(unknown, 0)

    def test_ris_matches_non_doi_extraction_by_source_id(self):
        source_id = "https://openalex.org/W1"
        candidates = [{
            "title": "No DOI paper", "doi": "", "source_id": source_id,
            "oa_url": "https://example.org/paper.pdf", "year": "2024", "abstract": "abstract",
        }]
        extractions = [{
            "doi": "", "source_id": source_id, "oa_url": candidates[0]["oa_url"],
            "doc": source_id, "identity_type": "source_id", "variable": "v",
            "valeur": "x", "citation": "x", "section": "Results",
        }]
        ris = report.generate_ris(extractions, candidates)
        self.assertIn("No DOI paper", ris)
        self.assertIn(f"ID  - {source_id}", ris)

    def test_missing_codebook_refuses_report_before_llm_or_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_report_review(root, codebook="")
            (root / "protocol.md").write_text("# Protocol sans codebook\n", encoding="utf-8")
            manifest_before = (root / "manifest.json").read_bytes()
            with patch.object(report, "_call_llm_report", side_effect=AssertionError("LLM interdit")):
                with self.assertRaises(RuntimeError):
                    report.main(rid, use_mock=False)
            self.assertFalse((root / "report.md").exists())
            self.assertFalse((root / "prisma.md").exists())
            self.assertEqual((root / "manifest.json").read_bytes(), manifest_before)

    def test_incoherent_cell_count_refuses_report_and_report_done(self):
        rows = [{
            "doi": "10.1234/one", "source_id": "", "oa_url": "", "doc": "10.1234/one",
            "identity_type": "doi", "variable": "variable", "valeur": "value",
            "citation": "citation", "section": "Results",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_report_review(root, fulltext_retrieved=2, included=2,
                                     extraction_rows=rows, extraction_articles=2)
            manifest_before = (root / "manifest.json").read_bytes()
            with self.assertRaises(RuntimeError):
                report.main(rid, use_mock=True)
            self.assertFalse((root / "report.md").exists())
            self.assertEqual((root / "manifest.json").read_bytes(), manifest_before)

    def test_zero_fulltext_with_valid_codebook_produces_explicit_empty_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_report_review(root, fulltext_retrieved=0, included=0,
                                     extraction_articles=0)
            report.main(rid, use_mock=True)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            content = (root / "report.md").read_text(encoding="utf-8")
            self.assertEqual(manifest["stage"], "report_done")
            self.assertIn("Textes intégraux récupérés | 0", content)
            self.assertIn("Articles avec donnée exploitable | 0", content)
            self.assertIn("Articles sans donnée exploitable | 0", content)

    def test_fixture_24_cells_has_distinct_article_and_cell_counts(self):
        rows = []
        for index in range(24):
            value = "value" if index < 17 else "NON TROUVÉ" if index < 19 else "CITATION REJETÉE"
            rows.append({
                "doi": f"10.1234/{index}", "source_id": "", "oa_url": "",
                "doc": f"10.1234/{index}", "identity_type": "doi",
                "variable": "technique_principale", "valeur": value,
                "citation": "citation" if value == "value" else "",
                "section": "Results",
            })
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_report_review(
                root, codebook="- **technique_principale** : description\n",
                fulltext_retrieved=24, included=24, extraction_rows=rows,
                extraction_articles=24,
            )
            report.main(rid, use_mock=True)
            content = (root / "report.md").read_text(encoding="utf-8")
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("Articles soumis à l'extraction | 24", content)
            self.assertIn("Articles avec donnée exploitable | 17", content)
            self.assertIn("Cellules tentées | 24", content)
            self.assertIn("Valeurs exploitables | 17", content)
            self.assertIn("NON TROUVÉ | 2", content)
            self.assertIn("Citations rejetées | 5", content)
            self.assertEqual(prisma["articles_with_data"], 17)
            self.assertEqual(prisma["cells_attempted"], 24)
            self.assertEqual(manifest["articles_with_data"], 17)
            self.assertEqual(manifest["cells_attempted"], 24)

    def test_multiple_variables_keep_articles_and_cells_distinct(self):
        rows = []
        for doc in ("10.1234/a", "10.1234/b"):
            for variable in ("v1", "v2"):
                rows.append({
                    "doi": doc, "source_id": "", "oa_url": "", "doc": doc,
                    "identity_type": "doi", "variable": variable, "valeur": "value",
                    "citation": "citation", "section": "Results",
                })
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_report_review(
                root, codebook="- **v1** : one\n- **v2** : two\n",
                fulltext_retrieved=2, included=2, extraction_rows=rows,
                extraction_articles=2,
            )
            report.main(rid, use_mock=True)
            content = (root / "report.md").read_text(encoding="utf-8")
            self.assertIn("Articles avec donnée exploitable | 2", content)
            self.assertIn("Cellules tentées | 4", content)

    def test_llm_context_labels_documents_and_cells_explicitly(self):
        extractions = [{
            "doc": "10.1234/a", "identity_type": "doi", "variable": "v",
            "valeur": "value", "citation": "citation", "section": "Results",
        }]
        with patch.object(report, "_call_llm_report", return_value="synthesis") as call:
            result = report.llm_synthesize({
                "question": "Question",
                "review_mode": "scoping",
                "extractions": extractions,
                "documents": {"articles_submitted": 1},
                "cells": {"v": {"cells_attempted": 1}},
            })
        self.assertEqual(result, "synthesis")
        user_message = call.call_args.args[1]
        self.assertIn("documents (articles)", user_message)
        self.assertIn("cells (article-variable rows)", user_message)
        self.assertIn("cells attempted: 1", user_message)
        self.assertNotIn("evaluated articles", user_message)


if __name__ == "__main__":
    unittest.main()
