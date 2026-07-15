#!/usr/bin/env python3
"""Replay v0 assessments with the v0 full-document matcher and v1 normalizer."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable


EXPERIMENT_DIR = Path(__file__).resolve().parent
V0_DIR = EXPERIMENT_DIR.parent / "hometest-criteria-matrix-v0"
V0_RESULTS_DIR = V0_DIR / "results" / "20260715T103329Z"
sys.path.insert(0, str(EXPERIMENT_DIR))

from run_microtest import VALID_STATUSES, normalize_span  # noqa: E402


def old_normalize_span(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def validate_v0_assessment(
    content: str,
    case: dict[str, Any],
    expected_ids: list[str],
    matcher: Callable[[str], str],
) -> bool:
    try:
        assessment = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(assessment, dict):
        return False
    if set(assessment) != {"schema", "criteria"}:
        return False
    if assessment.get("schema") != "criterion_assessment.v0-microtest":
        return False
    rows = assessment.get("criteria")
    if not isinstance(rows, list):
        return False
    if [row.get("id") if isinstance(row, dict) else None for row in rows] != expected_ids:
        return False

    sources = {
        "title": str(case.get("title", "") or ""),
        "abstract": str(case.get("abstract", "") or ""),
    }
    for row in rows:
        if not isinstance(row, dict):
            return False
        if set(row) != {"id", "status", "evidence", "reason"}:
            return False
        status = row.get("status")
        if status not in VALID_STATUSES:
            return False
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            return False
        if status == "not_reported" and evidence:
            return False
        if status in {"met", "not_met", "unclear"} and not evidence:
            return False
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"source", "quote"}:
                return False
            source = item.get("source")
            quote = item.get("quote")
            if source not in sources or not isinstance(quote, str) or not quote.strip():
                return False
            # Deliberately no sentence IDs and no ellipsis rejection: this is
            # the v0 full-title/full-abstract semantics requested by the replay.
            if matcher(quote) not in matcher(sources[source]):
                return False
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            return False
    return True


def main() -> int:
    cases_path = V0_RESULTS_DIR / "cases.jsonl"
    assessments_dir = V0_RESULTS_DIR / "assessments"
    criteria_path = V0_DIR / "criteria.json"
    if not cases_path.is_file() or not assessments_dir.is_dir():
        raise RuntimeError(f"v0 results are inaccessible under {V0_RESULTS_DIR}")

    cases = {}
    with cases_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                case = json.loads(line)
                cases[case["case_id"]] = case
    criteria_document = json.loads(criteria_path.read_text(encoding="utf-8"))
    expected_ids = [
        item["id"]
        for item in criteria_document["criteria"]
        if item["evaluator"] == "llm"
    ]

    for assessment_path in sorted(assessments_dir.glob("*.jsonl")):
        rows = []
        with assessment_path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        before = 0
        after = 0
        for row in rows:
            case = cases[row["case_id"]]
            content = row.get("model_content", "")
            if validate_v0_assessment(content, case, expected_ids, old_normalize_span):
                before += 1
            if validate_v0_assessment(content, case, expected_ids, normalize_span):
                after += 1
        print(f"{assessment_path.stem}: before={before}/{len(rows)} after={after}/{len(rows)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
