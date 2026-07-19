from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review.py"
SPEC = importlib.util.spec_from_file_location("sysrev_review_identity", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class ReviewIdentityTests(unittest.TestCase):
    def test_human_decisions_for_no_doi_cases_keep_distinct_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "to_review.jsonl").write_text(
                "\n".join(json.dumps({
                    "doc": doc, "identity_type": "source_id", "source_id": doc,
                    "doi": "", "oa_url": f"https://example.org/{doc}.pdf",
                    "title": doc, "score": 0.5, "reason": "ambiguous",
                }) for doc in ("W1", "W2")) + "\n",
                encoding="utf-8",
            )
            (root / "decisions.jsonl").write_text("", encoding="utf-8")
            (root / "prisma.json").write_text("{}", encoding="utf-8")
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
            review.apply_decisions(rid, {"W1": "include", "W2": "exclude"})

            entries = [json.loads(line) for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual({entry["doc"] for entry in entries}, {"W1", "W2"})
            self.assertTrue(all(entry["doc"] for entry in entries))
            self.assertEqual((root / "to_review.jsonl").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
