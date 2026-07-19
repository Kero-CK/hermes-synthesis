"""Tests for the screening precondition barrier.

The tests use temporary review directories and never call an LLM or network
endpoint.  Refused runs are checked for both side effects and screening calls.
"""

from __future__ import annotations

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
SPEC = importlib.util.spec_from_file_location("sysrev_screen_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


MISSING = object()


def review_fixture(review_dir: Path, search_status=MISSING, *, candidates: str = "sentinel\n"):
    (review_dir / "inputs" / "pdfs").mkdir(parents=True)
    (review_dir / "protocol.md").write_text(
        "# Critères\n" + "Critère de test suffisamment long. " * 8,
        encoding="utf-8",
    )
    manifest = {"id": "fixture", "stage": "dedup_done"}
    if search_status is not MISSING:
        manifest["search_status"] = search_status
    (review_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (review_dir / "candidates.csv").write_text(candidates, encoding="utf-8")
    (review_dir / "decisions.jsonl").write_text("decisions sentinel\n", encoding="utf-8")
    (review_dir / "to_review.jsonl").write_text("review sentinel\n", encoding="utf-8")
    (review_dir / "prisma.json").write_text("{\"sentinel\": true}\n", encoding="utf-8")

    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
    tracked = {
        name: (review_dir / name).read_bytes()
        for name in (
            "decisions.jsonl",
            "to_review.jsonl",
            "prisma.json",
            "manifest.json",
            "candidates.csv",
        )
    }
    return rid, tracked


class ScreenBarrierTests(unittest.TestCase):
    def test_complete_is_accepted_and_empty_results_keep_current_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            rid, _ = review_fixture(
                review_dir,
                "complete",
                candidates="title,abstract,doi\n",
            )
            mock_screen = Mock()
            with patch.object(screen, "mock_screen", mock_screen):
                with redirect_stdout(io.StringIO()) as stdout:
                    result = screen.main(rid, use_mock=True)

            self.assertIsNone(result)
            self.assertIn("Aucun candidat à screener", stdout.getvalue())
            mock_screen.assert_not_called()

    def test_non_complete_statuses_are_refused_without_side_effects_or_screening(self):
        statuses = ["incomplete", "capped", "error", "unknown", MISSING]
        for status in statuses:
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as temp_dir:
                    review_dir = Path(temp_dir)
                    rid, before = review_fixture(review_dir, status)
                    mock_screen = Mock()
                    llm_screen = Mock()
                    with patch.object(screen, "mock_screen", mock_screen), \
                            patch.object(screen, "llm_screen", llm_screen):
                        with redirect_stderr(io.StringIO()) as stderr:
                            with self.assertRaises(SystemExit) as raised:
                                screen.main(rid, use_mock=True)

                    self.assertEqual(raised.exception.code, 1)
                    message = stderr.getvalue()
                    self.assertIn("search_status", message)
                    self.assertIn("corpus ne peut pas être screené comme s'il était complet", message)
                    self.assertIn("Corrige ou relance la recherche", message)
                    if status == "capped":
                        self.assertIn("HARD_LIMIT", message)
                    mock_screen.assert_not_called()
                    llm_screen.assert_not_called()
                    after = {
                        name: (review_dir / name).read_bytes()
                        for name in before
                    }
                    self.assertEqual(after, before)

    def test_force_does_not_bypass_search_status_barrier(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            rid, _ = review_fixture(review_dir, "incomplete")
            with patch.object(screen, "mock_screen", Mock()) as mock_screen:
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        screen.main(rid, use_mock=True, force=True)

            self.assertEqual(raised.exception.code, 1)
            mock_screen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
