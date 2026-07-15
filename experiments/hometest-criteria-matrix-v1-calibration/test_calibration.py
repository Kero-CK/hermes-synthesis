#!/usr/bin/env python3
"""Direct tests for the offline calibration harness and analysis rules."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
CALIBRATION_DIR = Path(__file__).resolve().parent
REPO_DIR = CALIBRATION_DIR.parents[1]
FIXTURE_DIR = REPO_DIR / "examples" / "calib-selfimprove"

sys.path.insert(0, str(CALIBRATION_DIR))

from analyze_calibration import (  # noqa: E402
    CANDIDATE_CRITERIA,
    analyze,
    evaluate_candidate_rules,
    prepare_records,
    sample_rule3_instances,
    sampling_key,
)
from run_calibration import (  # noqa: E402
    FrozenIntegrityError,
    build_calibration_cases,
    check_frozen_integrity,
    load_csv_rows,
    microtest_dois,
)


class CalibrationTests(unittest.TestCase):
    def test_case_construction_preserves_fixture_order_and_membership(self) -> None:
        source_rows = load_csv_rows(FIXTURE_DIR / "gold_set.csv")
        cases = build_calibration_cases(FIXTURE_DIR)

        self.assertEqual(len(source_rows), 24)
        self.assertEqual(len(cases), len(source_rows))
        self.assertEqual(
            [case["case_id"] for case in cases],
            [f"gold_{index:03d}" for index in range(1, 25)],
        )
        self.assertEqual(
            [case["doi"] for case in cases],
            [row["doi"] for row in source_rows],
        )
        known_dois = microtest_dois()
        self.assertEqual(
            [case["in_microtest"] for case in cases],
            [str(row["doi"]).strip().lower() in known_dois for row in source_rows],
        )

    def test_frozen_integrity_passes_and_falsified_manifest_fails_loudly(self) -> None:
        integrity = check_frozen_integrity()
        self.assertEqual(
            integrity["reference_manifest"]["prompt_sha256"],
            integrity["prompt_sha256"],
        )

        with tempfile.TemporaryDirectory(
            prefix=".test-integrity-", dir=CALIBRATION_DIR
        ) as temporary:
            falsified_manifest = Path(temporary) / "run_manifest.json"
            reference = dict(integrity["reference_manifest"])
            reference["prompt_sha256"] = "0" * 64
            falsified_manifest.write_text(
                json.dumps(reference), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                FrozenIntegrityError, "frozen prompt integrity check failed"
            ):
                check_frozen_integrity(reference_manifest_path=falsified_manifest)

    @staticmethod
    def _record(
        case_id: str,
        doi: str,
        label: str,
        criterion_id: str,
        *,
        valid: bool = True,
        in_microtest: bool = False,
    ) -> dict[str, object]:
        return {
            "case_id": case_id,
            "doi": doi,
            "human_label": label,
            "hard_fails": [criterion_id],
            "validation_errors": [] if valid else ["requires evidence"],
            "coherence_errors": [],
            "phase1_route": "include" if label == "include" else "needs_manual",
            "in_microtest": in_microtest,
        }

    def test_rules_one_and_two_are_applied_to_valid_records(self) -> None:
        calibration_raw = [
            self._record("inc_1", "10.1/inc", "include", "E1_NO_ACTIONABLE_TECHNIQUE"),
            self._record("exc_1", "10.1/shared", "exclude", "E2_MODEL_TRAINING_ONLY"),
            self._record("exc_2_variant", "10.1/shared", "exclude", "E2_MODEL_TRAINING_ONLY"),
            self._record("exc_3", "10.1/exc3", "exclude", "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"),
            self._record("exc_4", "10.1/exc4", "exclude", "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"),
            self._record(
                "inc_invalid",
                "10.1/inc-invalid",
                "include",
                "I1_PROMPT_TECHNIQUE",
                valid=False,
            ),
        ]
        microtest_raw = [
            self._record(
                "micro_1",
                "10.1/shared",
                "exclude",
                "E2_MODEL_TRAINING_ONLY",
                in_microtest=True,
            )
        ]
        shared_results = evaluate_candidate_rules(
            prepare_records(calibration_raw, None, "calibration"),
            prepare_records(microtest_raw, None, "microtest_v1"),
        )

        self.assertEqual(
            shared_results["E2_MODEL_TRAINING_ONLY"]["status"], "not_qualified"
        )
        self.assertEqual(
            shared_results["E2_MODEL_TRAINING_ONLY"]["unique_doi_support"], 1
        )
        self.assertEqual(
            shared_results["E2_MODEL_TRAINING_ONLY"]["exclude_support"], 3
        )

        expanded_microtest_raw = microtest_raw + [
            self._record(
                "micro_2",
                "10.1/distinct-2",
                "exclude",
                "E2_MODEL_TRAINING_ONLY",
                in_microtest=True,
            ),
            self._record(
                "micro_3",
                "10.1/distinct-3",
                "exclude",
                "E2_MODEL_TRAINING_ONLY",
                in_microtest=True,
            ),
        ]
        results = evaluate_candidate_rules(
            prepare_records(calibration_raw, None, "calibration"),
            prepare_records(expanded_microtest_raw, None, "microtest_v1"),
        )

        self.assertEqual(results["E1_NO_ACTIONABLE_TECHNIQUE"]["status"], "disqualified")
        self.assertEqual(results["E2_MODEL_TRAINING_ONLY"]["status"], "qualified")
        self.assertEqual(results["E2_MODEL_TRAINING_ONLY"]["unique_doi_support"], 3)
        self.assertEqual(results["E2_MODEL_TRAINING_ONLY"]["exclude_support"], 5)
        self.assertEqual(
            results["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"]["status"],
            "not_qualified",
        )
        self.assertEqual(results["I1_PROMPT_TECHNIQUE"]["status"], "not_qualified")

    def test_rule_three_sampling_is_deterministic_and_excludes_microtest(self) -> None:
        micro_doi = sorted(microtest_dois())[0]
        rows = [
            self._record(
                f"sample_{index}",
                f"10.2/{index}",
                "exclude",
                "E2_MODEL_TRAINING_ONLY",
            )
            for index in range(7)
        ]
        rows.append(
            self._record(
                "microtest",
                micro_doi,
                "exclude",
                "E2_MODEL_TRAINING_ONLY",
                in_microtest=True,
            )
        )
        prepared = prepare_records(rows, None, "calibration")
        first = sample_rule3_instances(
            prepared,
            "E2_MODEL_TRAINING_ONLY",
            excluded_dois={micro_doi},
        )
        second = sample_rule3_instances(
            prepared,
            "E2_MODEL_TRAINING_ONLY",
            excluded_dois={micro_doi},
        )

        self.assertEqual([row["case_id"] for row in first], [row["case_id"] for row in second])
        self.assertEqual(len(first), 5)
        self.assertNotIn("microtest", [row["case_id"] for row in first])
        expected = sorted(
            [row for row in prepared if row["case_id"] != "microtest"],
            key=lambda row: (sampling_key(row, "E2_MODEL_TRAINING_ONLY"), row["case_id"]),
        )[:5]
        self.assertEqual(
            [row["case_id"] for row in first],
            [row["case_id"] for row in expected],
        )

    def test_offline_analysis_writes_report_and_empty_verdict_fields(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".test-analysis-", dir=CALIBRATION_DIR
        ) as temporary:
            results_dir = Path(temporary)
            (results_dir / "assessments").mkdir()
            cases = []
            assessments = []
            for index in range(1, 4):
                case_id = f"gold_{index:03d}"
                doi = f"10.3/{index}"
                cases.append(
                    {
                        "case_id": case_id,
                        "doi": doi,
                        "title": f"Calibration title {index}",
                        "stratum": "A",
                        "abstract_source_original": "fixture",
                    }
                )
                assessments.append(
                    {
                        "case_id": case_id,
                        "doi": doi,
                        "model": "deepseek-reasoner",
                        "variant": "title_abstract",
                        "human_label": "exclude",
                        "stratum": "A",
                        "validation_errors": [],
                        "coherence_errors": [],
                        "hard_fails": ["E2_MODEL_TRAINING_ONLY"],
                        "phase1_route": "needs_manual",
                        "full_assessment": [
                            {
                                "id": "E2_MODEL_TRAINING_ONLY",
                                "status": "met",
                                "evidence": [{"source": "S1", "quote": "training only"}],
                                "reason": "The abstract describes training only.",
                            }
                        ],
                    }
                )
            cases.append(
                {
                    "case_id": "gold_004",
                    "doi": "10.3/include",
                    "title": "Included calibration title",
                    "stratum": "B",
                    "abstract_source_original": "openalex",
                }
            )
            assessments.append(
                {
                    "case_id": "gold_004",
                    "doi": "10.3/include",
                    "model": "deepseek-reasoner",
                    "variant": "title_abstract",
                    "human_label": "include",
                    "stratum": "B",
                    "validation_errors": [],
                    "coherence_errors": [],
                    "hard_fails": [],
                    "phase1_route": "include",
                    "full_assessment": [],
                }
            )
            assessments.append(
                {
                    "case_id": "gold_005",
                    "doi": "10.3/invalid",
                    "model": "deepseek-reasoner",
                    "variant": "title_abstract",
                    "human_label": "include",
                    "validation_errors": ["E1 requires evidence when met"],
                    "coherence_errors": [],
                    "hard_fails": ["E1_NO_ACTIONABLE_TECHNIQUE"],
                    "phase1_route": "invalid_assessment",
                    "full_assessment": [],
                }
            )
            (results_dir / "cases.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in cases),
                encoding="utf-8",
            )
            (results_dir / "assessments" / "deepseek-reasoner.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in assessments),
                encoding="utf-8",
            )
            microtest_path = results_dir / "microtest.jsonl"
            microtest_path.write_text("", encoding="utf-8")

            result = analyze(results_dir, microtest_path)
            report = result["report_path"].read_text(encoding="utf-8")
            checklist = result["checklist_path"].read_text(encoding="utf-8")

            self.assertEqual(
                result["candidate_results"]["E2_MODEL_TRAINING_ONLY"]["status"],
                "qualified",
            )
            self.assertEqual(result["simulation"]["include_records_routed_exclude"], 0)
            self.assertIn("requires evidence", report)
            self.assertIn("Unique DOI support", report)
            self.assertIn("training only", checklist)
            self.assertIn("Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ", checklist)
            self.assertIn("## Synthèse Phase 2", checklist)


if __name__ == "__main__":
    unittest.main()
