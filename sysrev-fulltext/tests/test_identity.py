from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_fulltext_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fulltext)


FIELDS = ["title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status", "source", "query", "date"]


def make_review(root: Path) -> tuple[str, str]:
    (root / "inputs" / "pdfs").mkdir(parents=True)
    row = {
        "title": "No DOI paper", "doi": "", "source_id": "https://openalex.org/W123",
        "year": "2024", "abstract": "", "oa_url": "https://example.org/paper.pdf",
        "pdf_status": "", "source": "openalex", "query": "q", "date": "",
    }
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(row)
    entries = [{
        "doc": row["source_id"], "stage": "screen_title_abstract", "decision": "include",
        "identity_type": "source_id", "source_id": row["source_id"], "oa_url": row["oa_url"],
    }]
    (root / "decisions.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text(json.dumps({"id": "fulltext", "stage": "review_done"}), encoding="utf-8")
    (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
    return rid, row["source_id"]


class FulltextIdentityTests(unittest.TestCase):
    def test_doi_filename_keeps_historical_convention(self):
        self.assertEqual(fulltext.safe_document_filename("10.1234/example", "doi"), "10.1234_example")

    def test_oa_url_retrieval_and_windows_safe_identity_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, source_id = make_review(root)
            pdf = root / "fake.pdf"
            pdf.write_bytes(b"pdf")
            with patch.object(fulltext, "download_pdf", return_value=str(pdf)), \
                    patch.object(fulltext, "parse_pdf_real", return_value="x" * 600):
                fulltext.main(rid, use_mock=False)

            safe = fulltext.safe_document_filename(source_id, "source_id")
            self.assertTrue((root / "sources" / f"{safe}.md").exists())
            entries = [json.loads(line) for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
            retrieved = [entry for entry in entries if entry.get("stage") == "fulltext"]
            self.assertEqual(len(retrieved), 1)
            self.assertEqual(retrieved[0]["doc"], source_id)
            self.assertTrue(all(entry.get("doc") for entry in retrieved))

    def test_selection_keeps_two_no_doi_documents_distinct(self):
        entries = [
            {"doc": "W1", "stage": "screen_title_abstract", "decision": "include"},
            {"doc": "W2", "stage": "screen_title_abstract", "decision": "include"},
        ]
        docs, unknown = fulltext.select_included_dois(entries)
        self.assertEqual(docs, ["W1", "W2"])
        self.assertEqual(unknown, 0)

    def test_existing_markdown_is_reused_without_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, source_id = make_review(root)
            sources = root / "sources"
            sources.mkdir()
            safe = fulltext.safe_document_filename(source_id, "source_id")
            (sources / f"{safe}.md").write_text("cached markdown " * 40, encoding="utf-8")

            with patch.object(fulltext, "download_pdf", side_effect=AssertionError("download forbidden")), \
                    patch.object(fulltext, "parse_pdf_real", side_effect=AssertionError("parse forbidden")):
                fulltext.main(rid, use_mock=False)

            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("stage") == "fulltext"
            ]
            self.assertEqual(entries[-1]["decision"], "retrieved")
            self.assertIn("réutilisé", entries[-1]["reason"])
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_retrieved"], 1)
            self.assertEqual(prisma["fulltext_not_retrieved"], 0)

    def test_foreign_markdown_is_not_counted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            sources = root / "sources"
            sources.mkdir()
            (sources / "foreign-article.md").write_text("old article " * 60, encoding="utf-8")

            with patch.object(fulltext, "download_pdf", return_value=None):
                fulltext.main(rid, use_mock=False)

            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_assessed"], 1)
            self.assertEqual(prisma["fulltext_retrieved"], 0)
            self.assertEqual(prisma["fulltext_not_retrieved"], 1)

    def test_empty_current_corpus_does_not_retain_historical_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            (root / "decisions.jsonl").write_text(
                json.dumps({"doc": "https://openalex.org/W123",
                            "stage": "screen_title_abstract", "decision": "exclude"}) + "\n",
                encoding="utf-8",
            )
            (root / "sources" ).mkdir()
            (root / "sources" / "foreign.md").write_text("old article " * 60, encoding="utf-8")
            (root / "prisma.json").write_text(
                json.dumps({"fulltext_assessed": 99, "fulltext_retrieved": 99,
                            "fulltext_not_retrieved": 0}), encoding="utf-8"
            )

            fulltext.main(rid, use_mock=False)

            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_assessed"], 0)
            self.assertEqual(prisma["fulltext_retrieved"], 0)
            self.assertEqual(prisma["fulltext_not_retrieved"], 0)
            self.assertEqual(manifest["stage"], "fulltext_done")
            self.assertEqual(manifest["fulltext_success"], 0)


if __name__ == "__main__":
    unittest.main()
