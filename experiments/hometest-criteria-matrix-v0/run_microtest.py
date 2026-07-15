#!/usr/bin/env python3
"""Frozen-prompt micro-test for criterion-level screening assessments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_REVIEW_DIR = Path(
    "/vault/Projets/Hermes Synthesis/Reviews/hometest-prompteng"
)
SCHEMA = "criterion_assessment.v0-microtest"
VALID_STATUSES = {"met", "not_met", "unclear", "not_reported"}
VALID_SOURCES = {"title", "abstract"}
AUTO_EXCLUDABLE: set[str] = set()

CASE_SPECS = [
    {
        "case_id": "fp_prompt_tuning",
        "doi": "10.48550/arxiv.2304.07919",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_hard_fail": "I4_PRACTITIONER",
    },
    {
        "case_id": "fp_agent_planning",
        "doi": "10.1109/iccv51070.2023.00280",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_hard_fail": "I1_PROMPT_TECHNIQUE",
    },
    {
        "case_id": "fp_ranking_evaluation",
        "doi": "10.18653/v1/2023.emnlp-main.923",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_hard_fail": "I2_REPRODUCIBLE",
    },
    {
        "case_id": "tp_cot_counterfactual",
        "doi": "10.18653/v1/2023.findings-emnlp.101",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_hard_fail": None,
    },
    {
        "case_id": "tp_low_resource_prompting",
        "doi": "10.1016/j.nlp.2024.100124",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_hard_fail": None,
    },
    {
        "case_id": "tp_when_cot_needed",
        "doi": "10.48550/arxiv.2304.03262",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_hard_fail": None,
    },
    {
        "case_id": "state_boundary_ai_literacy",
        "doi": "10.1016/j.caeai.2024.100225",
        "category": "state_coverage_boundary",
        "variant": "title_abstract",
        "expected_hard_fail": None,
    },
    {
        "case_id": "state_title_only_true_positive",
        "doi": "10.18653/v1/2023.findings-emnlp.101",
        "category": "state_coverage_title_only_projection",
        "variant": "title_only_projection",
        "expected_hard_fail": None,
    },
    {
        "case_id": "state_title_only_prompt_tuning",
        "doi": "10.48550/arxiv.2304.07919",
        "category": "state_coverage_title_only_projection",
        "variant": "title_only_projection",
        "expected_hard_fail": None,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument(
        "--models",
        default="deepseek-reasoner,deepseek-chat",
        help="Comma-separated OpenAI-compatible model identifiers.",
    )
    return parser.parse_args()


def load_csv_by_doi(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    indexed = {row.get("doi", "").strip().lower(): row for row in rows}
    if "" in indexed:
        del indexed[""]
    return indexed


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_span(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def sanitize_document(text: str) -> str:
    return text.replace("<DOCUMENT>", "<DOC>").replace("</DOCUMENT>", "</DOC>")


def build_cases(review_dir: Path) -> list[dict[str, Any]]:
    gold = load_csv_by_doi(review_dir / "gold_set.csv")
    candidates = load_csv_by_doi(review_dir / "candidates.csv")
    cases: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        key = spec["doi"].lower()
        if key not in gold:
            raise RuntimeError(f"Gold-set DOI missing: {spec['doi']}")
        gold_row = gold[key]
        metadata = candidates.get(key, {})
        abstract = gold_row.get("abstract", "")
        if spec["variant"] == "title_only_projection":
            abstract = ""
        cases.append(
            {
                **spec,
                "title": gold_row.get("title", ""),
                "abstract": abstract,
                "human_label": gold_row.get("label", ""),
                "abstract_source_original": gold_row.get("abstract_source", ""),
                "publication_year": metadata.get("publication_year", ""),
                "language": metadata.get("language", ""),
            }
        )
    return cases


def build_prompt(prompt_template: str, llm_criteria: list[dict[str, Any]]) -> str:
    criteria_for_prompt = [
        {"id": item["id"], "kind": item["kind"], "text": item["text"]}
        for item in llm_criteria
    ]
    return prompt_template.replace(
        "{{CRITERIA_JSON}}",
        json.dumps(criteria_for_prompt, ensure_ascii=False, indent=2),
    )


def build_user_message(case: dict[str, Any]) -> str:
    abstract = case["abstract"] or "(no abstract supplied)"
    return (
        "<DOCUMENT>\n"
        f"Title: {sanitize_document(case['title'])}\n"
        f"Abstract: {sanitize_document(abstract)}\n"
        "</DOCUMENT>"
    )


def call_api(
    endpoint: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
) -> dict[str, Any]:
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code}: {detail[:1000]}") from exc


def parse_content(raw_response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    choices = raw_response.get("choices") or []
    if not choices:
        raise ValueError("Response has no choices")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise ValueError("Response truncated with finish_reason=length")
    content = choice.get("message", {}).get("content", "")
    if not content:
        raise ValueError("Response content is empty")
    return content, json.loads(content)


def validate_model_assessment(
    assessment: dict[str, Any],
    case: dict[str, Any],
    llm_criteria: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if set(assessment) != {"schema", "criteria"}:
        errors.append("top-level fields must be exactly schema and criteria")
    if assessment.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    rows = assessment.get("criteria")
    if not isinstance(rows, list):
        return errors + ["criteria must be an array"]

    expected_ids = [criterion["id"] for criterion in llm_criteria]
    actual_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if actual_ids != expected_ids:
        errors.append(f"criterion order/coverage mismatch: {actual_ids!r}")

    sources = {"title": case["title"], "abstract": case["abstract"]}
    for index, row in enumerate(rows):
        prefix = f"criteria[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(row) != {"id", "status", "evidence", "reason"}:
            errors.append(f"{prefix} fields are invalid")
        status = row.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{prefix}.status is invalid: {status!r}")
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"{prefix}.evidence must be an array")
            continue
        if status == "not_reported" and evidence:
            errors.append(f"{prefix}: not_reported forbids evidence")
        if status in {"met", "not_met", "unclear"} and not evidence:
            errors.append(f"{prefix}: {status} requires evidence")
        for evidence_index, item in enumerate(evidence):
            evidence_prefix = f"{prefix}.evidence[{evidence_index}]"
            if not isinstance(item, dict) or set(item) != {"source", "quote"}:
                errors.append(f"{evidence_prefix} fields are invalid")
                continue
            source = item.get("source")
            quote = item.get("quote")
            if source not in VALID_SOURCES:
                errors.append(f"{evidence_prefix}.source is invalid: {source!r}")
                continue
            if not isinstance(quote, str) or not quote.strip():
                errors.append(f"{evidence_prefix}.quote is empty")
                continue
            if normalize_span(quote) not in normalize_span(sources[source]):
                errors.append(f"{evidence_prefix}.quote not found in {source}")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"{prefix}.reason is empty")
    return errors


def metadata_assessments(
    case: dict[str, Any], metadata_criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for criterion in metadata_criteria:
        if criterion["id"] == "I5_ENGLISH":
            language = case["language"].strip().lower()
            if not language:
                status = "not_reported"
                evidence: list[dict[str, str]] = []
                reason = "Language metadata is missing."
            elif language in {"en", "eng", "english"}:
                status = "met"
                evidence = [{"source": "metadata", "quote": f"language: {case['language']}"}]
                reason = "Candidate metadata identifies the language as English."
            else:
                status = "not_met"
                evidence = [{"source": "metadata", "quote": f"language: {case['language']}"}]
                reason = "Candidate metadata identifies a non-English language."
        elif criterion["id"] == "I6_AFTER_2020":
            year_text = case["publication_year"].strip()
            if not year_text:
                status = "not_reported"
                evidence = []
                reason = "Publication-year metadata is missing."
            else:
                year = int(year_text)
                status = "met" if year > 2020 else "not_met"
                evidence = [{"source": "metadata", "quote": f"publication_year: {year_text}"}]
                reason = (
                    "Publication year is after 2020."
                    if status == "met"
                    else "Publication year is 2020 or earlier."
                )
        else:
            raise RuntimeError(f"No deterministic evaluator for {criterion['id']}")
        rows.append(
            {
                "id": criterion["id"],
                "status": status,
                "evidence": evidence,
                "reason": reason,
            }
        )
    return rows


def derive_hard_fails(
    full_assessment: list[dict[str, Any]], criteria_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    hard_fails: list[str] = []
    for row in full_assessment:
        criterion = criteria_by_id[row["id"]]
        if criterion["kind"] == "inclusion" and row["status"] == "not_met":
            hard_fails.append(row["id"])
        elif criterion["kind"] == "exclusion" and row["status"] == "met":
            hard_fails.append(row["id"])
    return hard_fails


def derive_phase1_route(
    full_assessment: list[dict[str, Any]], criteria_by_id: dict[str, dict[str, Any]]
) -> str:
    hard_fails = derive_hard_fails(full_assessment, criteria_by_id)
    if any(criterion_id in AUTO_EXCLUDABLE for criterion_id in hard_fails):
        return "exclude"
    if hard_fails:
        return "needs_manual"
    for row in full_assessment:
        criterion = criteria_by_id[row["id"]]
        if row["status"] == "unclear":
            return "needs_manual"
        if criterion["kind"] == "inclusion" and row["status"] == "not_reported":
            return "needs_manual"
    return "include"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    endpoint = os.environ.get("LLM_API_ENDPOINT", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not endpoint or not api_key:
        raise RuntimeError("LLM_API_ENDPOINT and LLM_API_KEY are required")

    criteria_document = json.loads((EXPERIMENT_DIR / "criteria.json").read_text(encoding="utf-8"))
    criteria = criteria_document["criteria"]
    llm_criteria = [item for item in criteria if item["evaluator"] == "llm"]
    metadata_criteria = [item for item in criteria if item["evaluator"] == "metadata"]
    criteria_by_id = {item["id"]: item for item in criteria}
    if len(criteria_by_id) != len(criteria):
        raise RuntimeError("Duplicate criterion ID")

    prompt_template = (EXPERIMENT_DIR / "prompt.txt").read_text(encoding="utf-8")
    system_prompt = build_prompt(prompt_template, llm_criteria)
    prompt_hash = sha256_text(system_prompt)
    criteria_hash = sha256_text(
        json.dumps(criteria_document, ensure_ascii=False, sort_keys=True)
    )
    cases = build_cases(args.review_dir)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = EXPERIMENT_DIR / "results" / run_id
    write_jsonl(run_dir / "cases.jsonl", cases)
    write_json(
        run_dir / "run_manifest.json",
        {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "temperature": 0.0,
            "models": [item.strip() for item in args.models.split(",") if item.strip()],
            "prompt_sha256": prompt_hash,
            "criteria_sha256": criteria_hash,
            "assessment_schema": SCHEMA,
            "phase1_auto_excludable": [],
            "review_dir": str(args.review_dir),
            "notes": [
                "Phase 1 needs no criterion-level gold re-annotation.",
                "Phase 2 validates only produced hard_fails by human review.",
                "Title-only cases are explicit projections because the home-test gold set has no empty abstracts.",
                "Results falsify this frozen prompt/model combination only, not the architecture.",
            ],
        },
    )

    technical_failures: list[str] = []
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    for model in models:
        model_rows: list[dict[str, Any]] = []
        for case in cases:
            print(f"[{model}] {case['case_id']}", flush=True)
            user_message = build_user_message(case)
            raw_path = run_dir / "raw" / model / f"{case['case_id']}.json"
            try:
                raw_response = call_api(endpoint, api_key, model, system_prompt, user_message)
                write_json(raw_path, raw_response)
                content, model_assessment = parse_content(raw_response)
                validation_errors = validate_model_assessment(
                    model_assessment, case, llm_criteria
                )
            except Exception as exc:
                technical_failures.append(f"{model}/{case['case_id']}: {exc}")
                model_rows.append(
                    {
                        "case_id": case["case_id"],
                        "doi": case["doi"],
                        "model": model,
                        "technical_error": str(exc),
                    }
                )
                continue

            model_rows_by_id = {row["id"]: row for row in model_assessment.get("criteria", [])}
            ordered_model_rows = [
                model_rows_by_id[criterion["id"]]
                for criterion in llm_criteria
                if criterion["id"] in model_rows_by_id
            ]
            deterministic_rows = metadata_assessments(case, metadata_criteria)
            full_by_id = {row["id"]: row for row in ordered_model_rows + deterministic_rows}
            full_assessment = [
                full_by_id[criterion["id"]]
                for criterion in criteria
                if criterion["id"] in full_by_id
            ]
            hard_fails = (
                derive_hard_fails(full_assessment, criteria_by_id)
                if len(full_assessment) == len(criteria)
                else []
            )
            route = (
                derive_phase1_route(full_assessment, criteria_by_id)
                if not validation_errors and len(full_assessment) == len(criteria)
                else "invalid_assessment"
            )
            expected = case["expected_hard_fail"]
            if case["category"] == "known_reasoner_false_positive":
                acceptance = expected in hard_fails and not validation_errors
            elif case["category"] == "known_chat_low_score_true_positive":
                acceptance = not hard_fails and route in {"include", "needs_manual"} and not validation_errors
            else:
                acceptance = None
            model_rows.append(
                {
                    "case_id": case["case_id"],
                    "doi": case["doi"],
                    "model": model,
                    "category": case["category"],
                    "variant": case["variant"],
                    "human_label": case["human_label"],
                    "expected_hard_fail": expected,
                    "validation_errors": validation_errors,
                    "hard_fails": hard_fails,
                    "phase1_route": route,
                    "acceptance": acceptance,
                    "model_content": content,
                    "full_assessment": full_assessment,
                }
            )
        write_jsonl(run_dir / "assessments" / f"{model}.jsonl", model_rows)

    if technical_failures:
        write_json(run_dir / "technical_failures.json", technical_failures)
        print(f"FAIL_LOUD: {len(technical_failures)} technical failure(s). Results: {run_dir}", file=sys.stderr)
        return 2
    print(f"RESULTS_DIR={run_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
