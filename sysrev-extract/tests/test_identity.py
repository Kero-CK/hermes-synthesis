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
SPEC = importlib.util.spec_from_file_location("sysrev_extract_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


def make_review(root: Path) -> tuple[str, str]:
    (root / "sources").mkdir(parents=True)
    source_id = "https://openalex.org/W999"
    safe = extract.safe_document_filename(source_id, "source_id")
    (root / "sources" / f"{safe}.md").write_text("full text", encoding="utf-8")
    (root / "protocol.md").write_text(
        "# Protocol\n\n## Codebook d'extraction\n- **variable** : description\n## Fin\n",
        encoding="utf-8",
    )
    (root / "candidates.csv").write_text(
        "title,doi,source_id,year,abstract,oa_url\nPaper,,https://openalex.org/W999,2024,,https://example.org/paper.pdf\n",
        encoding="utf-8",
    )
    (root / "decisions.jsonl").write_text(
        json.dumps({"doc": source_id, "stage": "fulltext", "decision": "retrieved", "identity_type": "source_id"}) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(json.dumps({"id": "extract", "stage": "fulltext_done"}), encoding="utf-8")
    (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/"), source_id


class ExtractIdentityTests(unittest.TestCase):
    def test_extract_reuses_fulltext_identity_and_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, source_id = make_review(root)
            extract.main(rid, use_mock=True)
            with (root / "extraction.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["doc"], source_id)
            self.assertEqual(rows[0]["source_id"], source_id)
            self.assertEqual(rows[0]["doi"], "")
            self.assertEqual(rows[0]["identity_type"], "source_id")

    def test_no_retrieved_fulltext_still_finishes_with_empty_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "sources").mkdir(parents=True)
            (root / "protocol.md").write_text(
                "# Protocol\n\n## Codebook d'extraction\n- **variable** : description\n",
                encoding="utf-8",
            )
            (root / "decisions.jsonl").write_text(
                json.dumps({"doc": "W1", "stage": "fulltext", "decision": "retrieval_failed"}) + "\n",
                encoding="utf-8",
            )
            manifest = {"id": "empty", "stage": "fulltext_done"}
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "candidates.csv").write_text("title,doi,source_id,oa_url\nPaper,,W1,https://example.org/p.pdf\n", encoding="utf-8")
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
            extract.main(rid, use_mock=True)
            self.assertEqual((root / "extraction.csv").read_text(encoding="utf-8").count("\n"), 1)
            self.assertEqual(json.loads((root / "manifest.json").read_text(encoding="utf-8"))["stage"], "extract_done")

    def _run_with_fulltext_events(self, events: list[dict]) -> tuple[list[dict], dict]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        rid, source_id = make_review(root)
        (root / "decisions.jsonl").write_text(
            "\n".join(json.dumps(entry) for entry in events) + "\n", encoding="utf-8"
        )
        extract.main(rid, use_mock=True)
        with (root / "extraction.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        return rows, manifest

    def test_failure_then_success_makes_article_extractable(self):
        rows, _ = self._run_with_fulltext_events([
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieval_failed"},
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieved"},
        ])
        self.assertEqual(len(rows), 1)

    def test_success_then_failure_makes_article_non_extractable(self):
        rows, manifest = self._run_with_fulltext_events([
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieved"},
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieval_failed"},
        ])
        self.assertEqual(rows, [])
        self.assertEqual(manifest["extraction_total"], 0)

    def test_multiple_successes_process_an_article_once(self):
        rows, _ = self._run_with_fulltext_events([
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieved"},
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "include"},
            {"doc": "https://openalex.org/W999", "stage": "fulltext", "decision": "retrieved"},
        ])
        self.assertEqual(len(rows), 1)

    def test_legacy_include_alias_and_identity_forms_are_resolved(self):
        for identity_type, doc in (
            ("doi", "10.1234/example"),
            ("source_id", "https://openalex.org/W1"),
            ("oa_url", "https://example.org/paper.pdf"),
        ):
            selected, unknown = extract.resolve_latest_fulltext([
                {"doc": doc, "stage": "fulltext", "decision": "include",
                 "identity_type": identity_type},
            ])
            self.assertEqual(unknown, 0)
            self.assertEqual([entry["doc"] for entry in selected], [doc])

    def test_unknown_later_entry_does_not_replace_latest_valid_event(self):
        selected, unknown = extract.resolve_latest_fulltext([
            {"doc": "W1", "stage": "fulltext", "decision": "retrieved"},
            {"doc": "W1", "stage": "fulltext", "decision": "unexpected"},
        ])
        self.assertEqual([entry["decision"] for entry in selected], ["retrieved"])
        self.assertEqual(unknown, 1)

    def test_missing_codebook_fails_before_llm_or_state_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            (root / "protocol.md").write_text("# Protocol sans codebook\n", encoding="utf-8")
            extraction_before = "existing extraction\n"
            (root / "extraction.csv").write_text(extraction_before, encoding="utf-8")
            manifest_before = (root / "manifest.json").read_bytes()
            decisions_before = (root / "decisions.jsonl").read_bytes()

            with patch.object(extract, "llm_extract", side_effect=AssertionError("LLM interdit")):
                with self.assertRaises(RuntimeError):
                    extract.main(rid, use_mock=False)

            self.assertEqual((root / "extraction.csv").read_text(encoding="utf-8"), extraction_before)
            self.assertEqual((root / "manifest.json").read_bytes(), manifest_before)
            self.assertEqual((root / "decisions.jsonl").read_bytes(), decisions_before)

    def test_multiple_variables_count_cells_and_articles_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, source_id = make_review(root)
            (root / "protocol.md").write_text(
                "# Protocol\n\n## Codebook d'extraction\n"
                "- **supported** : supported variable\n"
                "- **missing** : missing variable\n",
                encoding="utf-8",
            )

            def fake_extract(_text, variable_name, _description, _doc):
                if variable_name == "supported":
                    return {"valeur": "value", "citation": "full text", "section": "Results"}
                return {"valeur": "NON TROUVÉ", "citation": "", "section": ""}

            with patch.object(extract, "mock_extract", side_effect=fake_extract):
                extract.main(rid, use_mock=True)

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["extraction_cells_expected"], 2)
            self.assertEqual(manifest["extraction_cells_attempted"], 2)
            self.assertEqual(manifest["extraction_values"], 1)
            self.assertEqual(manifest["extraction_not_found"], 1)
            self.assertEqual(manifest["extraction_articles"], 1)
            self.assertEqual(manifest["extraction_articles_with_data"], 1)
            self.assertEqual(source_id, "https://openalex.org/W999")


if __name__ == "__main__":
    unittest.main()
