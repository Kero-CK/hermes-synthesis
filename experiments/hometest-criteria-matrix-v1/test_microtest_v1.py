#!/usr/bin/env python3
"""Direct-executable unit tests for the v1 micro-test harness."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from run_microtest import (  # noqa: E402
    CASE_SPECS,
    SCHEMA,
    AssessmentValidationError,
    _base_case_dois,
    build_user_message,
    coherence_errors,
    normalize_span,
    parse_content,
    segment_sentences,
    select_holdout_cases,
    validate_model_assessment,
)


def llm_criteria() -> list[dict[str, str]]:
    document = json.loads(
        (EXPERIMENT_DIR / "criteria.json").read_text(encoding="utf-8")
    )
    return [item for item in document["criteria"] if item["evaluator"] == "llm"]


def assessment_with_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"schema": SCHEMA, "criteria": rows}


class MicrotestV1Tests(unittest.TestCase):
    def test_normalize_span_positive_and_negative_cases(self) -> None:
        self.assertIn(
            normalize_span("17.7%"),
            normalize_span(r"accuracy increased from 17.7\% to 78.7\%"),
        )
        self.assertIn(normalize_span("students'"), normalize_span("students’ results"))
        self.assertIn(normalize_span("we propose"), normalize_span("We propose a method"))
        self.assertNotIn(normalize_span("combines"), normalize_span("combining"))
        self.assertNotIn(normalize_span("using"), normalize_span("uses"))

    def test_ellipsis_is_rejected_even_when_present_in_source(self) -> None:
        criteria = llm_criteria()
        case = {
            "title": "A title",
            "sentences": [{"source": "S1", "text": "The source literally has ... here."}],
        }
        rows = [
            {
                "id": criterion["id"],
                "status": "not_reported",
                "evidence": [],
                "reason": "No evidence.",
            }
            for criterion in criteria
        ]
        rows[0] = {
            "id": criteria[0]["id"],
            "status": "met",
            "evidence": [{"source": "S1", "quote": "..."}],
            "reason": "The source contains the span.",
        }
        errors = validate_model_assessment(
            assessment_with_rows(rows), case, criteria
        )
        self.assertTrue(any("quote contains ellipsis" in error for error in errors))

    def test_cross_sentence_quote_is_rejected(self) -> None:
        criteria = llm_criteria()
        case = {
            "title": "A title",
            "sentences": [
                {"source": "S1", "text": "First sentence."},
                {"source": "S2", "text": "Second sentence."},
                {"source": "S3", "text": "Third sentence."},
            ],
        }
        rows = [
            {
                "id": criterion["id"],
                "status": "not_reported",
                "evidence": [],
                "reason": "No evidence.",
            }
            for criterion in criteria
        ]
        rows[0] = {
            "id": criteria[0]["id"],
            "status": "met",
            "evidence": [
                {"source": "S2", "quote": "Second sentence. Third"}
            ],
            "reason": "The span crosses a sentence boundary.",
        }
        errors = validate_model_assessment(
            assessment_with_rows(rows), case, criteria
        )
        self.assertTrue(any("quote not found in S2" in error for error in errors))

    def test_sentence_segmentation_guard_url_and_sup(self) -> None:
        abstract = (
            "We report i.e., one example. "
            "We report e.g. Examples. "
            "Next result. Visit https://example.org"
        )
        sentences = segment_sentences(abstract)
        self.assertEqual(len(sentences), 4)
        self.assertTrue(any("i.e., one example" in sentence for sentence in sentences))
        self.assertTrue(any("e.g. Examples." in sentence for sentence in sentences))
        self.assertEqual(sentences[-1], "Visit https://example.org")

        residual = segment_sentences("Method works. <sup>1</sup>")
        self.assertEqual(residual, ["Method works.", "<sup>1</sup>"])

    def test_user_message_uses_sentence_ids(self) -> None:
        message = build_user_message(
            {
                "title": "A title",
                "sentences": [{"source": "S1", "text": "A sentence."}],
            }
        )
        self.assertEqual(
            message,
            "<DOCUMENT>\nT: A title\nS1: A sentence.\n</DOCUMENT>",
        )

    def test_duplicate_keys_are_validation_errors(self) -> None:
        content = (
            '{"schema":"criterion_assessment.v1-microtest",'
            '"criteria":[{"id":"I1_PROMPT_TECHNIQUE",'
            '"status":"not_reported","evidence":[],"evidence":[],'
            '"reason":"No evidence."}]}'
        )
        with self.assertRaises(AssessmentValidationError) as context:
            parse_content({"choices": [{"message": {"content": content}}]})
        self.assertIn("duplicate JSON key: evidence", str(context.exception))

    def test_each_coherence_rule_has_failing_and_passing_direction(self) -> None:
        cases = [
            (
                {"E1_NO_ACTIONABLE_TECHNIQUE": "met", "I1_PROMPT_TECHNIQUE": "met"},
                {"E1_NO_ACTIONABLE_TECHNIQUE": "met", "I1_PROMPT_TECHNIQUE": "not_reported"},
            ),
            (
                {"E3_BENCHMARK_ONLY": "met", "I2_REPRODUCIBLE": "met"},
                {"E3_BENCHMARK_ONLY": "met", "I2_REPRODUCIBLE": "not_met"},
            ),
            (
                {
                    "E4_APPLICATION_WITHOUT_PROMPT_DETAIL": "met",
                    "I2_REPRODUCIBLE": "met",
                },
                {
                    "E4_APPLICATION_WITHOUT_PROMPT_DETAIL": "met",
                    "I2_REPRODUCIBLE": "not_reported",
                },
            ),
            (
                {"E2_MODEL_TRAINING_ONLY": "met", "I4_PRACTITIONER": "met"},
                {"E2_MODEL_TRAINING_ONLY": "met", "I4_PRACTITIONER": "not_met"},
            ),
            (
                {"I4_PRACTITIONER": "met", "I1_PROMPT_TECHNIQUE": "not_met"},
                {"I4_PRACTITIONER": "met", "I1_PROMPT_TECHNIQUE": "not_reported"},
            ),
        ]
        for failing, passing in cases:
            failing_rows = [
                {"id": criterion_id, "status": status}
                for criterion_id, status in failing.items()
            ]
            passing_rows = [
                {"id": criterion_id, "status": status}
                for criterion_id, status in passing.items()
            ]
            self.assertTrue(coherence_errors(failing_rows), failing)
            self.assertEqual(coherence_errors(passing_rows), [], passing)

    def test_holdout_selection_is_deterministic_and_excludes_base_dois(self) -> None:
        fixture = EXPERIMENT_DIR.parents[1] / "examples" / "calib-selfimprove" / "gold_set.csv"
        first = select_holdout_cases(fixture, _base_case_dois())
        second = select_holdout_cases(fixture, _base_case_dois())
        self.assertEqual(first, second)
        self.assertEqual(
            [case["case_id"] for case in first],
            [
                "holdout_exclude_1",
                "holdout_exclude_2",
                "holdout_exclude_3",
                "holdout_include_1",
                "holdout_include_2",
                "holdout_include_3",
            ],
        )
        base_dois = _base_case_dois()
        self.assertTrue(all(case["doi"].strip().lower() not in base_dois for case in first))
        self.assertTrue(all(case["abstract"].strip() for case in first))


if __name__ == "__main__":
    unittest.main()
