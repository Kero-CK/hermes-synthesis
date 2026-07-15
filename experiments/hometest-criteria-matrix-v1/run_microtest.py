#!/usr/bin/env python3
"""Frozen-prompt v1 micro-test harness for criterion-level screening."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_REVIEW_DIR = Path(
    "/vault/Projets/Hermes Synthesis/Reviews/hometest-prompteng"
)
SCHEMA = "criterion_assessment.v1-microtest"
VALID_STATUSES = {"met", "not_met", "unclear", "not_reported"}
AUTO_EXCLUDABLE: set[str] = set()

SENTENCE_SPLIT_REGEX = r"(?<=[.!?])\s+(?=[A-Z<])"
SENTENCE_SPLIT_RE = re.compile(SENTENCE_SPLIT_REGEX)
COMMON_ABBREVIATION_RE = re.compile(r"\b(?:i\.e\.|e\.g\.|etc\.)$", re.IGNORECASE)

MATCHER_SPEC = [
    "NFKC",
    "casefold",
    "replace U+2019 and U+2018 with ASCII apostrophe (')",
    'replace U+201C and U+201D with ASCII double quote (\")',
    r"replace \% with %, \& with &, \_ with _, and \# with #",
    "replace ~ with an ASCII space",
    "collapse whitespace runs to one ASCII space",
    "strip leading and trailing whitespace",
]

COHERENCE_RULES = [
    "E1_NO_ACTIONABLE_TECHNIQUE=met requires I1_PROMPT_TECHNIQUE in {not_met, not_reported}",
    "E3_BENCHMARK_ONLY=met requires I2_REPRODUCIBLE in {not_met, not_reported}",
    "E4_APPLICATION_WITHOUT_PROMPT_DETAIL=met requires I2_REPRODUCIBLE in {not_met, not_reported}",
    "E2_MODEL_TRAINING_ONLY=met requires I4_PRACTITIONER != met",
    "I4_PRACTITIONER=met requires I1_PROMPT_TECHNIQUE != not_met",
]

HOLDOUT_SELECTION_RULE = (
    "Read gold_set.csv under --review-dir; exclude DOI values already present "
    "in CASE_SPECS; keep only rows with a non-empty abstract; sort by the "
    "hexadecimal sha256(doi.lower()) value in ascending order; take the first "
    "three rows with label=exclude as holdout_exclude_1..3 and the first three "
    "rows with label=include as holdout_include_1..3; set category to "
    "holdout_exclude or holdout_include, variant to title_abstract, and both "
    "expected_primary and accepted_alternatives to null/empty; record this rule "
    "in the manifest before any API call."
)

CASE_SPECS = [
    {
        "case_id": "fp_prompt_tuning",
        "doi": "10.48550/arxiv.2304.07919",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_primary": "E2_MODEL_TRAINING_ONLY",
        "accepted_alternatives": ["I4_PRACTITIONER"],
    },
    {
        "case_id": "fp_agent_planning",
        "doi": "10.1109/iccv51070.2023.00280",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_primary": "I1_PROMPT_TECHNIQUE",
        "accepted_alternatives": ["E1_NO_ACTIONABLE_TECHNIQUE"],
    },
    {
        "case_id": "fp_ranking_evaluation",
        "doi": "10.18653/v1/2023.emnlp-main.923",
        "category": "known_reasoner_false_positive",
        "variant": "title_abstract",
        "expected_primary": "E3_BENCHMARK_ONLY",
        "accepted_alternatives": [
            "E1_NO_ACTIONABLE_TECHNIQUE",
            "E4_APPLICATION_WITHOUT_PROMPT_DETAIL",
        ],
    },
    {
        "case_id": "tp_cot_counterfactual",
        "doi": "10.18653/v1/2023.findings-emnlp.101",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
    {
        "case_id": "tp_low_resource_prompting",
        "doi": "10.1016/j.nlp.2024.100124",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
    {
        "case_id": "tp_when_cot_needed",
        "doi": "10.48550/arxiv.2304.03262",
        "category": "known_chat_low_score_true_positive",
        "variant": "title_abstract",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
    {
        "case_id": "state_boundary_ai_literacy",
        "doi": "10.1016/j.caeai.2024.100225",
        "category": "state_coverage_boundary",
        "variant": "title_abstract",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
    {
        "case_id": "state_title_only_true_positive",
        "doi": "10.18653/v1/2023.findings-emnlp.101",
        "category": "state_coverage_title_only_projection",
        "variant": "title_only_projection",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
    {
        "case_id": "state_title_only_prompt_tuning",
        "doi": "10.48550/arxiv.2304.07919",
        "category": "state_coverage_title_only_projection",
        "variant": "title_only_projection",
        "expected_primary": None,
        "accepted_alternatives": [],
    },
]


class AssessmentValidationError(ValueError):
    """A model response is malformed and must be recorded as validation_error."""

    def __init__(self, message: str, content: str = "") -> None:
        super().__init__(message)
        self.content = content


class DuplicateJSONKeyError(ValueError):
    """Raised by the JSON object-pairs hook for duplicate keys."""

    def __init__(self, key: str) -> None:
        super().__init__(f"duplicate JSON key: {key}")
        self.key = key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument(
        "--models",
        default="deepseek-reasoner,deepseek-chat",
        help="Comma-separated OpenAI-compatible model identifiers.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate artifacts without calling any API or writing results/.",
    )
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_csv_by_doi(path: Path) -> dict[str, dict[str, str]]:
    rows = load_csv_rows(path)
    indexed = {row.get("doi", "").strip().lower(): row for row in rows}
    indexed.pop("", None)
    return indexed


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_span(text: str) -> str:
    """Normalize an evidence span using the preregistered matcher sequence."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = (
        normalized.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
    normalized = (
        normalized.replace(r"\%", "%")
        .replace(r"\&", "&")
        .replace(r"\_", "_")
        .replace(r"\#", "#")
        .replace("~", " ")
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _ends_with_common_abbreviation(prefix: str) -> bool:
    return bool(COMMON_ABBREVIATION_RE.search(prefix.rstrip()))


def segment_sentences(abstract: str) -> list[str]:
    """Segment an abstract with the frozen regex and abbreviation guard."""

    text = abstract.strip()
    if not text:
        return []

    boundaries: list[tuple[int, int]] = []
    for match in SENTENCE_SPLIT_RE.finditer(text):
        if _ends_with_common_abbreviation(text[: match.start()]):
            continue
        boundaries.append((match.start(), match.end()))

    sentences: list[str] = []
    start = 0
    for boundary_start, boundary_end in boundaries:
        sentence = text[start:boundary_start].strip()
        if sentence:
            sentences.append(sentence)
        start = boundary_end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def sentence_records(abstract: str) -> list[dict[str, str]]:
    return [
        {"source": f"S{index}", "text": sentence}
        for index, sentence in enumerate(segment_sentences(abstract), start=1)
    ]


def sanitize_document(text: str) -> str:
    return text.replace("<DOCUMENT>", "<DOC>").replace("</DOCUMENT>", "</DOC>")


def _case_sentence_records(case: dict[str, Any]) -> list[dict[str, str]]:
    raw_records = case.get("sentences")
    if raw_records is None:
        return sentence_records(str(case.get("abstract", "") or ""))
    records: list[dict[str, str]] = []
    for index, item in enumerate(raw_records, start=1):
        if isinstance(item, dict):
            source = str(item.get("source") or f"S{index}")
            text = str(item.get("text") or "")
        else:
            source = f"S{index}"
            text = str(item)
        records.append({"source": source, "text": text})
    return records


def build_user_message(case: dict[str, Any]) -> str:
    lines = ["<DOCUMENT>", f"T: {sanitize_document(str(case.get('title', '')))}"]
    for sentence in _case_sentence_records(case):
        lines.append(
            f"{sentence['source']}: {sanitize_document(sentence['text'])}"
        )
    lines.append("</DOCUMENT>")
    return "\n".join(lines)


def build_prompt(prompt_template: str, llm_criteria: list[dict[str, Any]]) -> str:
    criteria_for_prompt = [
        {"id": item["id"], "kind": item["kind"], "text": item["text"]}
        for item in llm_criteria
    ]
    return prompt_template.replace(
        "{{CRITERIA_JSON}}",
        json.dumps(criteria_for_prompt, ensure_ascii=False, indent=2),
    )


def _canonical_doi(doi: str) -> str:
    return doi.strip().lower()


def _base_case_dois() -> set[str]:
    return {_canonical_doi(str(spec["doi"])) for spec in CASE_SPECS}


def select_holdout_cases(
    gold_path: Path, excluded_dois: set[str] | None = None
) -> list[dict[str, Any]]:
    """Select six held-out cases deterministically from gold_set.csv."""

    excluded = {
        _canonical_doi(doi) for doi in (excluded_dois or _base_case_dois())
    }
    candidates: list[tuple[str, int, dict[str, str]]] = []
    for row_index, row in enumerate(load_csv_rows(gold_path)):
        doi = row.get("doi", "") or ""
        abstract = row.get("abstract", "") or ""
        label = (row.get("label", "") or "").strip().lower()
        if not doi.strip() or not abstract.strip():
            continue
        if _canonical_doi(doi) in excluded:
            continue
        if label not in {"exclude", "include"}:
            continue
        # The preregistered key is sha256(doi.lower()); row order breaks only
        # an otherwise unspecified hash tie.
        candidates.append((sha256_text(doi.lower()), row_index, row))

    candidates.sort(key=lambda item: (item[0], item[1]))
    selected: list[dict[str, Any]] = []
    for label in ("exclude", "include"):
        matching = [
            row for _, _, row in candidates
            if (row.get("label", "") or "").strip().lower() == label
        ][:3]
        for index, row in enumerate(matching, start=1):
            abstract = row.get("abstract", "") or ""
            selected.append(
                {
                    "case_id": f"holdout_{label}_{index}",
                    "doi": row.get("doi", "") or "",
                    "category": f"holdout_{label}",
                    "variant": "title_abstract",
                    "expected_primary": None,
                    "accepted_alternatives": [],
                    "title": row.get("title", "") or "",
                    "abstract": abstract,
                    "human_label": row.get("label", "") or "",
                    "abstract_source_original": row.get("abstract_source", "") or "",
                    "publication_year": row.get("publication_year", "") or "",
                    "language": row.get("language", "") or "",
                    "sentences": sentence_records(abstract),
                }
            )
    return selected


def _case_from_gold(
    spec: dict[str, Any],
    gold_row: dict[str, str],
    candidates: dict[str, dict[str, str]],
) -> dict[str, Any]:
    key = _canonical_doi(str(spec["doi"]))
    metadata = candidates.get(key, {})
    abstract = gold_row.get("abstract", "") or ""
    if spec["variant"] == "title_only_projection":
        abstract = ""
    return {
        **spec,
        "title": gold_row.get("title", "") or "",
        "abstract": abstract,
        "human_label": gold_row.get("label", "") or "",
        "abstract_source_original": gold_row.get("abstract_source", "") or "",
        "publication_year": metadata.get("publication_year", "") or "",
        "language": metadata.get("language", "") or "",
        "sentences": sentence_records(abstract),
    }


def build_cases(
    review_dir: Path, *, allow_missing_base: bool = False
) -> list[dict[str, Any]]:
    gold_path = review_dir / "gold_set.csv"
    if not gold_path.is_file():
        raise RuntimeError(f"gold_set.csv is inaccessible: {gold_path}")
    gold = load_csv_by_doi(gold_path)
    candidates_path = review_dir / "candidates.csv"
    candidates = load_csv_by_doi(candidates_path) if candidates_path.is_file() else {}

    cases: list[dict[str, Any]] = []
    missing: list[str] = []
    for spec in CASE_SPECS:
        key = _canonical_doi(str(spec["doi"]))
        if key not in gold:
            missing.append(str(spec["doi"]))
            continue
        cases.append(_case_from_gold(spec, gold[key], candidates))
    if missing and not allow_missing_base:
        raise RuntimeError(f"Gold-set DOI(s) missing: {', '.join(missing)}")

    holdouts = select_holdout_cases(gold_path, _base_case_dois())
    for holdout in holdouts:
        metadata = candidates.get(_canonical_doi(str(holdout["doi"])), {})
        holdout["publication_year"] = metadata.get("publication_year", "") or ""
        holdout["language"] = metadata.get("language", "") or ""
    cases.extend(holdouts)
    return cases


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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(key)
        result[key] = value
    return result


def parse_content(raw_response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    choices = raw_response.get("choices") or []
    if not choices:
        raise AssessmentValidationError("response has no choices")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise AssessmentValidationError("response truncated with finish_reason=length")
    content = choice.get("message", {}).get("content", "")
    if not isinstance(content, str) or not content:
        raise AssessmentValidationError("response content is empty")
    try:
        parsed = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except DuplicateJSONKeyError as exc:
        raise AssessmentValidationError(str(exc), content) from exc
    except json.JSONDecodeError as exc:
        raise AssessmentValidationError(f"invalid JSON: {exc.msg}", content) from exc
    if not isinstance(parsed, dict):
        raise AssessmentValidationError("assessment JSON must be an object", content)
    return content, parsed


def _source_map(case: dict[str, Any]) -> dict[str, str]:
    sources = {"T": str(case.get("title", "") or "")}
    for sentence in _case_sentence_records(case):
        sources[sentence["source"]] = sentence["text"]
    return sources


def validate_model_assessment(
    assessment: dict[str, Any],
    case: dict[str, Any],
    llm_criteria: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(assessment, dict):
        return ["assessment must be an object"]
    if set(assessment) != {"schema", "criteria"}:
        errors.append("top-level fields must be exactly schema and criteria")
    if assessment.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    rows = assessment.get("criteria")
    if not isinstance(rows, list):
        return errors + ["criteria must be an array"]

    expected_ids = [criterion["id"] for criterion in llm_criteria]
    actual_ids = [row.get("id") if isinstance(row, dict) else None for row in rows]
    if actual_ids != expected_ids:
        errors.append(f"criterion order/coverage mismatch: {actual_ids!r}")

    sources = _source_map(case)
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
            if source not in sources:
                errors.append(f"{evidence_prefix}.source is invalid: {source!r}")
                continue
            if not isinstance(quote, str) or not quote.strip():
                errors.append(f"{evidence_prefix}.quote is empty")
                continue
            if "..." in quote or "…" in quote:
                errors.append(f"{evidence_prefix}: quote contains ellipsis")
                continue
            normalized_quote = normalize_span(quote)
            if not normalized_quote:
                errors.append(f"{evidence_prefix}.quote is empty after normalization")
                continue
            if normalized_quote not in normalize_span(sources[source]):
                errors.append(
                    f"{evidence_prefix}.quote not found in {source}"
                )
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"{prefix}.reason is empty")
    return errors


def coherence_errors(full_assessment: list[dict[str, Any]]) -> list[str]:
    """Return cross-criterion errors only when the relevant statuses are valid."""

    status_by_id: dict[str, str] = {}
    for row in full_assessment:
        if not isinstance(row, dict):
            return []
        status = row.get("status")
        if status not in VALID_STATUSES:
            return []
        criterion_id = row.get("id")
        if isinstance(criterion_id, str):
            status_by_id[criterion_id] = status

    errors: list[str] = []

    def available(*criterion_ids: str) -> bool:
        return all(criterion_id in status_by_id for criterion_id in criterion_ids)

    if (
        available("E1_NO_ACTIONABLE_TECHNIQUE", "I1_PROMPT_TECHNIQUE")
        and status_by_id["E1_NO_ACTIONABLE_TECHNIQUE"] == "met"
        and status_by_id["I1_PROMPT_TECHNIQUE"] not in {"not_met", "not_reported"}
    ):
        errors.append(
            "E1 requires I1_PROMPT_TECHNIQUE to be not_met or not_reported"
        )
    if (
        available("E3_BENCHMARK_ONLY", "I2_REPRODUCIBLE")
        and status_by_id["E3_BENCHMARK_ONLY"] == "met"
        and status_by_id["I2_REPRODUCIBLE"] not in {"not_met", "not_reported"}
    ):
        errors.append("E3 requires I2_REPRODUCIBLE to be not_met or not_reported")
    if (
        available("E4_APPLICATION_WITHOUT_PROMPT_DETAIL", "I2_REPRODUCIBLE")
        and status_by_id["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"] == "met"
        and status_by_id["I2_REPRODUCIBLE"] not in {"not_met", "not_reported"}
    ):
        errors.append("E4 requires I2_REPRODUCIBLE to be not_met or not_reported")
    if (
        available("E2_MODEL_TRAINING_ONLY", "I4_PRACTITIONER")
        and status_by_id["E2_MODEL_TRAINING_ONLY"] == "met"
        and status_by_id["I4_PRACTITIONER"] == "met"
    ):
        errors.append("E2 requires I4_PRACTITIONER to be different from met")
    if (
        available("I4_PRACTITIONER", "I1_PROMPT_TECHNIQUE")
        and status_by_id["I4_PRACTITIONER"] == "met"
        and status_by_id["I1_PROMPT_TECHNIQUE"] == "not_met"
    ):
        errors.append("I4 requires I1_PROMPT_TECHNIQUE to be different from not_met")
    return errors


def metadata_assessments(
    case: dict[str, Any], metadata_criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for criterion in metadata_criteria:
        if criterion["id"] == "I5_ENGLISH":
            language_raw = str(case.get("language", "") or "")
            language = language_raw.strip().lower()
            if not language:
                status = "not_reported"
                evidence: list[dict[str, str]] = []
                reason = "Language metadata is missing."
            elif language in {"en", "eng", "english"}:
                status = "met"
                evidence = [{"source": "metadata", "quote": f"language: {language_raw}"}]
                reason = "Candidate metadata identifies the language as English."
            else:
                status = "not_met"
                evidence = [{"source": "metadata", "quote": f"language: {language_raw}"}]
                reason = "Candidate metadata identifies a non-English language."
        elif criterion["id"] == "I6_AFTER_2020":
            year_text = str(case.get("publication_year", "") or "").strip()
            if not year_text:
                status = "not_reported"
                evidence = []
                reason = "Publication-year metadata is missing."
            elif not re.fullmatch(r"[0-9]{4}", year_text):
                status = "not_reported"
                evidence = []
                reason = "Publication-year metadata is not a four-digit year."
            else:
                status = "met" if int(year_text) > 2020 else "not_met"
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


def _current_git_commit() -> tuple[str, str | None]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=EXPERIMENT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return "", f"git_commit unavailable: {exc}"
    return completed.stdout.strip(), None


def _make_manifest(
    run_id: str,
    args: argparse.Namespace,
    models: list[str],
    prompt_hash: str,
    criteria_hash: str,
    cases: list[dict[str, Any]],
    warnings: list[str],
    git_commit: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "temperature": 0.0,
        "models": models,
        "prompt_sha256": prompt_hash,
        "criteria_sha256": criteria_hash,
        "assessment_schema": SCHEMA,
        "phase1_auto_excludable": [],
        "review_dir": str(args.review_dir),
        "dry_run": bool(args.dry_run),
        "git_commit": git_commit,
        "matcher_spec": MATCHER_SPEC,
        "sentence_segmentation_regex": SENTENCE_SPLIT_REGEX,
        "sentence_segmentation_abbreviation_guard": (
            r"do not split when the text immediately before the boundary ends with "
            r"\b(?:i\.e\.|e\.g\.|etc\.)$ (case-insensitive)"
        ),
        "coherence_rules": COHERENCE_RULES,
        "holdout_selection_rule": HOLDOUT_SELECTION_RULE,
        "oracle": [
            {
                "case_id": spec["case_id"],
                "category": spec["category"],
                "expected_primary": spec["expected_primary"],
                "accepted_alternatives": spec["accepted_alternatives"],
            }
            for spec in CASE_SPECS
        ],
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "messages_path": "user_messages.jsonl",
        "warnings": warnings,
        "notes": [
            "Phase 1 has no criterion-level gold re-annotation.",
            "Phase 2 verifies only produced hard-fails by human review.",
            "Title-only cases are explicit projections with an empty sentence list.",
            "A validation_error or coherence_error makes an assessment invalid for routing; coherence_errors also block acceptance, and holdout_exclude accepts only the non-include route rule.",
        ],
    }


def _assessment_rows(
    model_assessment: dict[str, Any],
    case: dict[str, Any],
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows = model_assessment.get("criteria", [])
    model_rows_by_id = {
        row["id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
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
    status_valid = bool(full_assessment) and all(
        isinstance(row.get("status"), str)
        and row["status"] in VALID_STATUSES
        for row in full_assessment
    )
    coherence = coherence_errors(full_assessment) if status_valid else []
    return full_assessment, coherence, ordered_model_rows


def _acceptance(
    case: dict[str, Any],
    hard_fails: list[str],
    route: str,
    validation_errors: list[str],
    coherence: list[str],
    assessment_complete: bool,
) -> bool | None:
    category = case["category"]
    if category in {
        "state_coverage_boundary",
        "state_coverage_title_only_projection",
    }:
        return None
    if category == "holdout_exclude":
        # The held-out exclude criterion is safety-oriented: any route other
        # than automatic include is a success. A coherence error is explicitly
        # disqualifying for acceptance by the preregistered coherence rule.
        if coherence:
            return False
        return route != "include"
    if validation_errors or coherence or not assessment_complete:
        return False
    if category == "known_reasoner_false_positive":
        primary = case.get("expected_primary")
        alternatives = set(case.get("accepted_alternatives") or [])
        return bool(
            primary in hard_fails or alternatives.intersection(hard_fails)
        )
    if category == "known_chat_low_score_true_positive":
        return not hard_fails and route in {"include", "needs_manual"}
    if category == "holdout_include":
        return not hard_fails
    return None


def _result_row_base(case: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "doi": case["doi"],
        "model": model,
        "category": case["category"],
        "variant": case["variant"],
        "human_label": case.get("human_label", ""),
        "expected_primary": case.get("expected_primary"),
        "accepted_alternatives": case.get("accepted_alternatives", []),
    }


def run_validator_self_test(llm_criteria: list[dict[str, Any]]) -> dict[str, Any]:
    case = {
        "title": "A validator self-test",
        "abstract": "The abstract has one sentence.",
        "sentences": [{"source": "S1", "text": "The abstract has one sentence."}],
    }
    rows = [
        {
            "id": criterion["id"],
            "status": "not_reported",
            "evidence": [],
            "reason": "No relevant evidence is present.",
        }
        for criterion in llm_criteria
    ]
    valid = {"schema": SCHEMA, "criteria": rows}
    valid_errors = validate_model_assessment(valid, case, llm_criteria)
    if valid_errors:
        raise AssertionError(f"validator self-test valid case failed: {valid_errors}")

    invalid = json.loads(json.dumps(valid))
    invalid["criteria"][0] = {
        "id": llm_criteria[0]["id"],
        "status": "met",
        "evidence": [{"source": "S1", "quote": "..."}],
        "reason": "Ellipsis must be rejected.",
    }
    invalid_errors = validate_model_assessment(invalid, case, llm_criteria)
    if not any("quote contains ellipsis" in error for error in invalid_errors):
        raise AssertionError("validator self-test did not reject ellipsis")
    return {
        "status": "pass",
        "valid_error_count": len(valid_errors),
        "invalid_error_count": len(invalid_errors),
    }


def _process_model_assessment(
    model_assessment: dict[str, Any],
    content: str,
    case: dict[str, Any],
    model: str,
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
    criteria_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    validation_errors = validate_model_assessment(
        model_assessment, case, llm_criteria
    )
    full_assessment, coherence, ordered_model_rows = _assessment_rows(
        model_assessment,
        case,
        criteria,
        llm_criteria,
        metadata_criteria,
    )
    assessment_complete = len(full_assessment) == len(criteria)
    hard_fails = (
        derive_hard_fails(full_assessment, criteria_by_id)
        if assessment_complete
        else []
    )
    route = (
        derive_phase1_route(full_assessment, criteria_by_id)
        if not validation_errors and not coherence and assessment_complete
        else "invalid_assessment"
    )
    result = _result_row_base(case, model)
    result.update(
        {
            "validation_errors": validation_errors,
            "coherence_errors": coherence,
            "hard_fails": hard_fails,
            "phase1_route": route,
            "acceptance": _acceptance(
                case,
                hard_fails,
                route,
                validation_errors,
                coherence,
                assessment_complete,
            ),
            "model_content": content,
            "full_assessment": full_assessment,
        }
    )
    return result


def main() -> int:
    args = parse_args()
    criteria_document = json.loads(
        (EXPERIMENT_DIR / "criteria.json").read_text(encoding="utf-8")
    )
    criteria = criteria_document["criteria"]
    llm_criteria = [item for item in criteria if item["evaluator"] == "llm"]
    metadata_criteria = [
        item for item in criteria if item["evaluator"] == "metadata"
    ]
    criteria_by_id = {item["id"]: item for item in criteria}
    if len(criteria_by_id) != len(criteria):
        raise RuntimeError("Duplicate criterion ID")

    prompt_template = (EXPERIMENT_DIR / "prompt.txt").read_text(encoding="utf-8")
    system_prompt = build_prompt(prompt_template, llm_criteria)
    prompt_hash = sha256_text(system_prompt)
    criteria_hash = sha256_text(
        json.dumps(criteria_document, ensure_ascii=False, sort_keys=True)
    )
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    warnings: list[str] = []

    if args.dry_run:
        try:
            cases = build_cases(args.review_dir, allow_missing_base=True)
        except Exception as exc:
            cases = []
            warnings.append(f"review data unavailable in dry-run: {exc}")
    else:
        endpoint = os.environ.get("LLM_API_ENDPOINT", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        if not endpoint or not api_key:
            raise RuntimeError("LLM_API_ENDPOINT and LLM_API_KEY are required")
        cases = build_cases(args.review_dir)

    git_commit, git_warning = _current_git_commit()
    if git_warning:
        warnings.append(git_warning)
        if args.dry_run:
            print(f"WARNING: {git_warning}", file=sys.stderr)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = "dryrun" if args.dry_run else "results"
    run_dir = EXPERIMENT_DIR / output_root / run_id
    write_jsonl(run_dir / "cases.jsonl", cases)
    user_messages = [
        {"case_id": case["case_id"], "message": build_user_message(case)}
        for case in cases
    ]
    write_jsonl(run_dir / "user_messages.jsonl", user_messages)
    manifest = _make_manifest(
        run_id,
        args,
        models,
        prompt_hash,
        criteria_hash,
        cases,
        warnings,
        git_commit,
    )
    write_json(run_dir / "run_manifest.json", manifest)

    if args.dry_run:
        self_test = run_validator_self_test(llm_criteria)
        write_json(run_dir / "validator_self_test.json", self_test)
        print(f"DRY_RUN_DIR={run_dir}")
        print("VALIDATOR_SELF_TEST=PASS")
        print(f"CASES={len(cases)}")
        return 0

    technical_failures: list[str] = []
    for model in models:
        model_rows: list[dict[str, Any]] = []
        for case in cases:
            print(f"[{model}] {case['case_id']}", flush=True)
            user_message = build_user_message(case)
            raw_path = run_dir / "raw" / model / f"{case['case_id']}.json"
            try:
                raw_response = call_api(
                    endpoint, api_key, model, system_prompt, user_message
                )
                write_json(raw_path, raw_response)
                content, model_assessment = parse_content(raw_response)
            except AssessmentValidationError as exc:
                result = _result_row_base(case, model)
                result.update(
                    {
                        "validation_errors": [str(exc)],
                        "coherence_errors": [],
                        "hard_fails": [],
                        "phase1_route": "invalid_assessment",
                        "acceptance": _acceptance(
                            case, [], "invalid_assessment", [str(exc)], [], False
                        ),
                        "model_content": exc.content,
                        "full_assessment": [],
                    }
                )
                model_rows.append(result)
                continue
            except Exception as exc:
                technical_failures.append(f"{model}/{case['case_id']}: {exc}")
                result = _result_row_base(case, model)
                result.update({"technical_error": str(exc)})
                model_rows.append(result)
                continue

            model_rows.append(
                _process_model_assessment(
                    model_assessment,
                    content,
                    case,
                    model,
                    criteria,
                    llm_criteria,
                    metadata_criteria,
                    criteria_by_id,
                )
            )
        write_jsonl(run_dir / "assessments" / f"{model}.jsonl", model_rows)

    if technical_failures:
        write_json(run_dir / "technical_failures.json", technical_failures)
        print(
            f"FAIL_LOUD: {len(technical_failures)} technical failure(s). Results: {run_dir}",
            file=sys.stderr,
        )
        return 2
    print(f"RESULTS_DIR={run_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
