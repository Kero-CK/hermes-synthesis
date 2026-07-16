#!/usr/bin/env python3
"""Tests for the terminal assisted calibration contract."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.dont_write_bytecode = True
FINAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FINAL_DIR))

import analyze_final_calibration as analyzer  # noqa: E402
import run_final_calibration as runner  # noqa: E402


class FinalCalibrationTests(unittest.TestCase):
    def _row(
        self,
        case_id: str,
        replicate: int,
        label: str,
        hard_fails: list[str],
        *,
        doi: str | None = None,
        valid: bool = True,
        variant: str = "title_abstract",
    ) -> dict[str, object]:
        case = {
            "case_id": case_id,
            "doi": doi or f"10.9999/{case_id}",
            "title": f"Title {case_id}",
            "human_label": label,
            "variant": variant,
        }
        return {
            "case_id": case_id,
            "doi": case["doi"],
            "model": "deepseek-reasoner",
            "bloc": "gold_set",
            "replicate": replicate,
            "variant": variant,
            "human_label": label,
            "validation_errors": [] if valid else ["requires evidence"],
            "coherence_errors": [],
            "hard_fails": hard_fails,
            "phase1_route": "needs_manual",
            "full_assessment": [],
            "_case": case,
            "_valid": valid,
            "_label": label,
            "_replicate": str(replicate),
            "_model": "deepseek-reasoner",
        }

    def _pair(
        self,
        case_id: str,
        label: str,
        first: list[str],
        second: list[str],
        **kwargs: object,
    ) -> list[dict[str, object]]:
        return [
            self._row(case_id, 1, label, first, **kwargs),
            self._row(case_id, 2, label, second, **kwargs),
        ]

    def test_integrity_passes_and_all_tampered_inputs_fail(self) -> None:
        integrity = runner.check_final_integrity()
        self.assertEqual(integrity["corpus_sha256"], runner.EXPECTED_CORPUS_SHA256)
        self.assertEqual(integrity["v3_prompt_sha256"], runner.EXPECTED_V3_PROMPT_SHA256)
        self.assertEqual(integrity["criteria_sha256"], runner.EXPECTED_CRITERIA_SHA256)

        with tempfile.TemporaryDirectory(dir=FINAL_DIR) as temporary:
            root = Path(temporary)
            tampered_corpus = root / "cases.jsonl"
            tampered_corpus.write_bytes(integrity["corpus_bytes"] + b"\n")
            with self.assertRaises(runner.FinalIntegrityError):
                runner.check_final_integrity(corpus_path=tampered_corpus)

            tampered_prompt = root / "prompt.txt"
            tampered_prompt.write_text(
                runner.V3_PROMPT_PATH.read_text(encoding="utf-8").replace(
                    "criterion_assessment.v3-microtest",
                    "criterion_assessment.v3-microtest-tampered",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(runner.v3_harness.FrozenIntegrityError):
                runner.check_final_integrity(v3_prompt_path=tampered_prompt)

            criteria = json.loads(runner.V1_CRITERIA_PATH.read_text(encoding="utf-8"))
            criteria["criteria"][0]["id"] = "TAMPERED_FINAL_ID"
            tampered_criteria = root / "criteria.json"
            tampered_criteria.write_text(json.dumps(criteria), encoding="utf-8")
            with self.assertRaises(runner.v3_harness.FrozenIntegrityError):
                runner.check_final_integrity(criteria_path=tampered_criteria)

    def test_exact_forty_cases_and_eighty_slots(self) -> None:
        _raw, cases = runner.load_frozen_cases()
        self.assertEqual(len(cases), 40)
        self.assertEqual(len(runner.replicate_slots(cases)), 80)
        self.assertEqual(len({case["case_id"] for case in cases}), 40)

    def test_reproduction_is_the_intersection_of_two_valid_replicates(self) -> None:
        rows = self._pair(
            "same",
            "exclude",
            ["I1_PROMPT_TECHNIQUE", "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"],
            ["I1_PROMPT_TECHNIQUE"],
        )
        rows += self._pair(
            "flip",
            "exclude",
            ["I1_PROMPT_TECHNIQUE"],
            ["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"],
        )
        rows += [self._row("one", 1, "exclude", ["I1_PROMPT_TECHNIQUE"])]
        reproduced = analyzer.reproduced_hard_fails(rows)
        self.assertEqual(reproduced[("deepseek-reasoner", "same")], {"I1_PROMPT_TECHNIQUE"})
        self.assertEqual(reproduced[("deepseek-reasoner", "flip")], set())
        self.assertEqual(reproduced[("deepseek-reasoner", "one")], set())

    def test_only_safe_i1_pairs_propose_and_everything_else_is_human(self) -> None:
        rows = self._pair(
            "safe",
            "exclude",
            ["I1_PROMPT_TECHNIQUE"],
            ["I1_PROMPT_TECHNIQUE"],
        )
        rows += self._pair(
            "include_i1",
            "include",
            ["I1_PROMPT_TECHNIQUE"],
            ["I1_PROMPT_TECHNIQUE"],
        )
        rows += self._pair(
            "include_e1e4",
            "include",
            ["E1_NO_ACTIONABLE_TECHNIQUE", "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"],
            ["E1_NO_ACTIONABLE_TECHNIQUE", "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"],
        )
        rows += self._pair(
            "title_only",
            "exclude",
            ["I1_PROMPT_TECHNIQUE"],
            ["I1_PROMPT_TECHNIQUE"],
            variant="title_only",
        )
        rows += self._pair(
            "invalid",
            "exclude",
            ["I1_PROMPT_TECHNIQUE"],
            ["I1_PROMPT_TECHNIQUE"],
            valid=False,
        )
        result = analyzer.simulate_assisted_policy(analyzer.pair_summaries(rows))
        self.assertEqual([item["case_id"] for item in result["proposals"]], ["safe"])
        self.assertEqual(
            {item["case_id"] for item in result["include_safety_violations"]},
            {"include_i1"},
        )
        human_ids = {item["case_id"] for item in result["human_routes"]}
        self.assertTrue({"include_e1e4", "title_only", "invalid"}.issubset(human_ids))
        self.assertTrue(all(item["final_decision"] == "needs_human_validation" for item in result["proposals"]))

    def test_rules_and_allowlist_guard(self) -> None:
        rows: list[dict[str, object]] = []
        for index in range(3):
            rows += self._pair(
                f"exclude_{index}",
                "exclude",
                ["I1_PROMPT_TECHNIQUE"],
                ["I1_PROMPT_TECHNIQUE"],
                doi=f"10.9999/distinct-{index}",
            )
        qualified = analyzer.apply_terminal_rules(analyzer.pair_summaries(rows))
        self.assertEqual(qualified["status"], "qualified")
        self.assertEqual(qualified["reproduced_exclude_unique_dois"], 3)
        self.assertEqual(len(qualified["rule_3_sample"]), 3)

        rows += self._pair(
            "include_hit",
            "include",
            ["I1_PROMPT_TECHNIQUE"],
            ["I1_PROMPT_TECHNIQUE"],
        )
        disqualified = analyzer.apply_terminal_rules(analyzer.pair_summaries(rows))
        self.assertEqual(disqualified["status"], "disqualified")
        with self.assertRaises(analyzer.PolicyError):
            analyzer.validate_allowlist({"E4_APPLICATION_WITHOUT_PROMPT_DETAIL"})

    def test_requested_and_response_models_are_distinct(self) -> None:
        args = argparse.Namespace(dry_run=True)
        integrity = runner.check_final_integrity()
        manifest = runner.build_manifest(
            args,
            "test-run",
            runner.REQUESTED_MODEL,
            integrity,
            integrity["cases"],
            "anchor-sha",
            ["deepseek-v4-flash"],
        )
        self.assertEqual(manifest["requested_model"], "deepseek-reasoner")
        self.assertEqual(manifest["response_models"], ["deepseek-v4-flash"])
        self.assertNotEqual(manifest["requested_model"], manifest["response_models"][0])

    def test_dry_run_never_calls_api(self) -> None:
        dryrun_root = runner.FINAL_DIR / "dryrun"
        before = set(dryrun_root.iterdir()) if dryrun_root.is_dir() else set()
        with patch.object(
            runner.v3_harness,
            "call_api",
            side_effect=AssertionError("API call made during dry-run"),
        ), patch.object(sys, "argv", ["run_final_calibration.py", "--dry-run"]):
            self.assertEqual(runner.main(), 0)
        after = set(dryrun_root.iterdir()) if dryrun_root.is_dir() else set()
        for path in after - before:
            shutil.rmtree(path)
        if dryrun_root.is_dir() and not any(dryrun_root.iterdir()):
            dryrun_root.rmdir()

    def test_offline_analysis_writes_report_and_checklist(self) -> None:
        with tempfile.TemporaryDirectory(dir=FINAL_DIR) as temporary:
            results = Path(temporary)
            (results / "assessments").mkdir()
            cases = []
            rows = []
            for index in range(1, 4):
                case_id = f"gold_{index:03d}"
                doi = f"10.9999/test-{index}"
                cases.append(
                    {
                        "case_id": case_id,
                        "doi": doi,
                        "title": f"Test title {index}",
                        "human_label": "exclude",
                        "variant": "title_abstract",
                    }
                )
                for replicate in (1, 2):
                    rows.append(
                        {
                            "case_id": case_id,
                            "doi": doi,
                            "model": "deepseek-reasoner",
                            "replicate": replicate,
                            "variant": "title_abstract",
                            "human_label": "exclude",
                            "validation_errors": [],
                            "coherence_errors": [],
                            "hard_fails": ["I1_PROMPT_TECHNIQUE"],
                            "full_assessment": [],
                        }
                    )
            (results / "cases.jsonl").write_text(
                "".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8"
            )
            (results / "assessments" / "deepseek-reasoner.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            (results / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "case_count": 2,
                        "requested_model": "deepseek-reasoner",
                        "response_models": ["deepseek-v4-flash"],
                        "prompt_sha256": runner.EXPECTED_V3_PROMPT_SHA256,
                        "criteria_sha256": runner.EXPECTED_CRITERIA_SHA256,
                        "corpus_sha256": runner.EXPECTED_CORPUS_SHA256,
                        "anchor_commit": "anchor",
                    }
                ),
                encoding="utf-8",
            )
            result = analyzer.analyze(results)
            report = result["report_path"].read_text(encoding="utf-8")
            checklist = result["checklist_path"].read_text(encoding="utf-8")
            self.assertIn("Requested model", report)
            self.assertIn("Response model identifiers", report)
            self.assertIn("pending_human_checklist", report)
            self.assertIn("Human verdict", checklist)


if __name__ == "__main__":
    unittest.main()
