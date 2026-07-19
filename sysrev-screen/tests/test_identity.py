from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "screen.py"
SPEC = importlib.util.spec_from_file_location("sysrev_screen_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


def make_review(root: Path, candidates: list[dict]) -> str:
    (root / "inputs" / "pdfs").mkdir(parents=True)
    (root / "protocol.md").write_text(
        "# Protocol\n\n## Critères d'inclusion\n- article\n\n" + "x" * 120,
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"id": "identity", "stage": "dedup_done", "search_status": "complete"}),
        encoding="utf-8",
    )
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status", "source", "query", "date"],
        )
        writer.writeheader()
        writer.writerows(candidates)
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "to_review.jsonl").write_text("", encoding="utf-8")
    (root / "prisma.json").write_text("{}", encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class IdentityScreenTests(unittest.TestCase):
    def test_no_doi_candidates_keep_distinct_source_identity(self):
        candidates = [
            {
                "title": "Same title",
                "doi": "",
                "source_id": "https://openalex.org/W1",
                "year": "2024",
                "abstract": "A",
                "oa_url": "https://example.org/one.pdf",
                "pdf_status": "",
                "source": "openalex",
                "query": "q",
                "date": "2026-07-18",
            },
            {
                "title": "Same title",
                "doi": "",
                "source_id": "https://openalex.org/W2",
                "year": "2024",
                "abstract": "B",
                "oa_url": "https://example.org/two.pdf",
                "pdf_status": "",
                "source": "openalex",
                "query": "q",
                "date": "2026-07-18",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            rid = make_review(Path(temp_dir), candidates)
            fake = Mock(side_effect=lambda title, abstract, doc, *_: {
                "score": 0.9,
                "reason": doc,
                "model": "mock@test",
            })
            with patch.object(screen, "mock_screen", fake), redirect_stdout(io.StringIO()):
                screen.main(rid, use_mock=True)

            entries = [
                json.loads(line)
                for line in (Path(temp_dir) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([entry["doc"] for entry in entries], [
                "https://openalex.org/W1", "https://openalex.org/W2"
            ])
            self.assertTrue(all(entry["doc"] for entry in entries))
            self.assertEqual(fake.call_count, 2)
            prisma = json.loads((Path(temp_dir) / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["included"], 2)

    def test_doi_identity_remains_the_decision_document(self):
        candidate = {
            "title": "DOI paper", "doi": "10.1234/example", "source_id": "W1",
            "year": "2024", "abstract": "A", "oa_url": "https://example.org/p.pdf",
            "pdf_status": "", "source": "openalex", "query": "q", "date": "2026-07-18",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            rid = make_review(Path(temp_dir), [candidate])
            fake = Mock(return_value={"score": 0.9, "reason": "ok", "model": "mock@test"})
            with patch.object(screen, "mock_screen", fake), redirect_stdout(io.StringIO()):
                screen.main(rid, use_mock=True)
            entry = json.loads((Path(temp_dir) / "decisions.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(entry["doc"], "10.1234/example")
            self.assertNotIn("identity_type", entry)
            self.assertEqual(fake.call_args.args[2], "10.1234/example")

    def test_candidate_without_any_identity_is_rejected_before_screening(self):
        candidate = {
            "title": "No identity",
            "doi": "",
            "source_id": "",
            "year": "2024",
            "abstract": "A",
            "oa_url": "",
            "pdf_status": "",
            "source": "openalex",
            "query": "q",
            "date": "2026-07-18",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            rid = make_review(Path(temp_dir), [candidate])
            fake = Mock()
            with patch.object(screen, "mock_screen", fake), redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    screen.main(rid, use_mock=True)
            self.assertEqual(raised.exception.code, 1)
            self.assertIn("source_id", stderr.getvalue())
            fake.assert_not_called()
            self.assertEqual((Path(temp_dir) / "decisions.jsonl").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
