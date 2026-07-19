from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "dedup.py"
SPEC = importlib.util.spec_from_file_location("sysrev_dedup_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
dedup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dedup)


FIELDS = ["title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status", "source", "query", "date"]


def make_review(root: Path, rows: list[dict]) -> str:
    (root / "inputs" / "pdfs").mkdir(parents=True)
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"id": "dedup", "stage": "search_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text("{}", encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class DedupIdentityTests(unittest.TestCase):
    def test_identical_titles_with_distant_years_are_not_merged(self):
        rows = [
            {"title": "Identical title", "doi": "", "source_id": "W1", "year": "2024", "abstract": "a", "oa_url": "https://x/1", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "Identical title", "doi": "", "source_id": "W2", "year": "2027", "abstract": "b", "oa_url": "https://x/2", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root, rows)
            dedup.main(rid)
            with (root / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                result = list(csv.DictReader(handle))
            with (root / "candidates_raw.csv").open(newline="", encoding="utf-8") as handle:
                raw = list(csv.DictReader(handle))
            self.assertEqual(len(result), 2)
            self.assertEqual({row["source_id"] for row in result}, {"W1", "W2"})
            self.assertIn("source_id", raw[0])

    def test_same_source_id_is_an_exact_duplicate_and_is_preserved(self):
        row = {"title": "A", "doi": "", "source_id": "W1", "year": "2024", "abstract": "long", "oa_url": "https://x/1", "pdf_status": "", "source": "openalex", "query": "q", "date": ""}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root, [row, dict(row, abstract="")])
            dedup.main(rid)
            with (root / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                result = list(csv.DictReader(handle))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["source_id"], "W1")

            audit = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0]["identity_type"], "source_id")
            self.assertEqual(audit[0]["merged_ids"], ["W1", "https://x/1"])
            self.assertEqual(audit[0]["merged_dois"], [])
            self.assertTrue(all(audit[0]["merged_ids"]))

    def _run_and_read(self, rows: list[dict], threshold: float = 0.90):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        rid = make_review(root, rows)
        dedup.main(rid, threshold=threshold)
        with (root / "candidates.csv").open(newline="", encoding="utf-8") as handle:
            result = list(csv.DictReader(handle))
        audit = [
            json.loads(line)
            for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return root, result, audit

    def test_chemrxiv_versions_merge_by_normalized_title(self):
        rows = [
            {"title": "ChemRxiv: Reliable Agent Planning", "doi": "10.1000/chem-v2", "source_id": "W-V2", "year": "2024", "abstract": "", "oa_url": "https://x/v2", "pdf_status": "", "source": "chemrxiv", "query": "q", "date": ""},
            {"title": "chemrxiv reliable agent planning", "doi": "10.1000/chem-v3", "source_id": "W-V3", "year": "2025", "abstract": "abstract v3", "oa_url": "https://x/v3", "pdf_status": "", "source": "chemrxiv", "query": "q", "date": ""},
            {"title": "ChemRxiv — Reliable Agent Planning", "doi": "10.1000/chem-v4", "source_id": "W-V4", "year": "2024", "abstract": "abstract v4", "oa_url": "https://x/v4", "pdf_status": "", "source": "chemrxiv", "query": "q", "date": ""},
        ]
        root, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["doi"], "10.1000/chem-v3")
        self.assertEqual(len(audit), 1)
        self.assertIn("titre normalisé identique", audit[0]["reason"])
        self.assertEqual(set(audit[0]["merged_dois"]), {row["doi"] for row in rows})
        self.assertEqual(set(audit[0]["merged_ids"]), {
            value for row in rows for _, value in dedup.row_identity_values(row)
        })
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["stage"], "dedup_done")
        self.assertEqual(manifest["dedup_removed"], 2)
        self.assertEqual(prisma["after_dedup"], 1)
        with (root / "candidates_raw.csv").open(newline="", encoding="utf-8") as handle:
            raw = list(csv.DictReader(handle))
        self.assertEqual(len(raw), 3)

    def test_meic_published_and_arxiv_merge_with_adjacent_years(self):
        rows = [
            {"title": "MEIC: Multi-Agent Evaluation in Context", "doi": "10.1000/meic-published", "source_id": "W-MEIC-P", "year": "2024", "abstract": "published", "oa_url": "https://x/meic-p", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "MEIC multi agent evaluation in context", "doi": "10.48550/arxiv.2401.00001", "source_id": "W-MEIC-A", "year": "2023", "abstract": "preprint", "oa_url": "https://x/meic-a", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
        ]
        _, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("10.1000/meic-published", audit[0]["merged_dois"])
        self.assertIn("10.48550/arxiv.2401.00001", audit[0]["merged_dois"])

    def test_topic_classification_published_and_arxiv_merge(self):
        rows = [
            {"title": "Topic Classification of Case Law", "doi": "10.1000/caselaw-published", "source_id": "W-CASE-P", "year": "2024", "abstract": "published", "oa_url": "https://x/case-p", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "Topic  Classification of Case Law.", "doi": "10.48550/arxiv.2402.00002", "source_id": "W-CASE-A", "year": "", "abstract": "preprint", "oa_url": "https://x/case-a", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
        ]
        _, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("titre normalisé identique", audit[0]["reason"])

    def test_same_doi_merges_even_when_titles_differ(self):
        rows = [
            {"title": "Published title", "doi": "10.1000/same", "source_id": "W-P", "year": "2024", "abstract": "published", "oa_url": "https://x/p", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "Preprint title", "doi": "10.1000/same", "source_id": "W-A", "year": "2023", "abstract": "", "oa_url": "https://x/a", "pdf_status": "", "source": "arxiv", "query": "q", "date": ""},
        ]
        _, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["abstract"], "published")
        self.assertIn("doi", audit[0]["reason"])

    def test_approximate_titles_with_two_different_dois_do_not_merge(self):
        rows = [
            {"title": "Reliability analysis for language model agents", "doi": "10.1000/reliability-a", "source_id": "W-A", "year": "2024", "abstract": "a", "oa_url": "https://x/a", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "Reliability analysis for language model agent systems", "doi": "10.1000/reliability-b", "source_id": "W-B", "year": "2025", "abstract": "b", "oa_url": "https://x/b", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
        ]
        _, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(audit, [])

    def test_similar_titles_merge_when_one_doi_is_missing(self):
        rows = [
            {"title": "Prompt engineering for reliable agents", "doi": "10.1000/prompt-a", "source_id": "W-A", "year": "2024", "abstract": "a", "oa_url": "https://x/a", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
            {"title": "Prompt engineering for reliability agents", "doi": "", "source_id": "W-B", "year": "2025", "abstract": "", "oa_url": "https://x/b", "pdf_status": "", "source": "arxiv", "query": "q", "date": ""},
        ]
        _, result, audit = self._run_and_read(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("ratio=", audit[0]["reason"])

    def test_missing_identity_is_rejected_without_writing_dedup_result(self):
        rows = [
            {"title": "No identity", "doi": "", "source_id": "", "year": "2024", "abstract": "", "oa_url": "", "pdf_status": "", "source": "openalex", "query": "q", "date": ""},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root, rows)
            with self.assertRaises(ValueError):
                dedup.main(rid)


if __name__ == "__main__":
    unittest.main()
