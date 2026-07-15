#!/usr/bin/env python3
"""Offline analysis for a completed criteria-matrix v1 calibration run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True
CALIBRATION_DIR = Path(__file__).resolve().parent
V1_DIR = CALIBRATION_DIR.parent / "hometest-criteria-matrix-v1"
DEFAULT_MICROTEST_ASSESSMENTS = (
    V1_DIR
    / "results"
    / "20260715T135629864224Z"
    / "assessments"
    / "deepseek-reasoner.jsonl"
)
sys.path.insert(0, str(CALIBRATION_DIR))

from run_calibration import (  # noqa: E402
    CANDIDATE_CRITERIA,
    RULE_1_TEXT,
    RULE_2_TEXT,
    RULE_3_TEXT,
    canonical_doi,
    microtest_dois,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument(
        "--microtest-assessments",
        type=Path,
        default=DEFAULT_MICROTEST_ASSESSMENTS,
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_cases(results_dir: Path) -> dict[str, dict[str, Any]]:
    path = results_dir / "cases.jsonl"
    if not path.is_file():
        raise RuntimeError(f"cases.jsonl is missing: {path}")
    return {row["case_id"]: row for row in load_jsonl(path)}


def assessment_is_valid(row: dict[str, Any]) -> bool:
    return (
        "technical_error" not in row
        and row.get("validation_errors") == []
        and row.get("coherence_errors") == []
    )


def record_label(row: dict[str, Any]) -> str:
    return str(row.get("human_label", "") or "").strip().lower()


def record_doi(row: dict[str, Any]) -> str:
    return canonical_doi(str(row.get("doi", "") or ""))


def prepare_records(
    rows: Iterable[dict[str, Any]],
    cases: dict[str, dict[str, Any]] | None,
    origin: str,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        case = (cases or {}).get(str(row.get("case_id", ""))) or {}
        item["_case"] = case
        item["_origin"] = origin
        item["_valid"] = assessment_is_valid(row)
        item["_label"] = record_label(row)
        if not item.get("doi"):
            item["doi"] = case.get("doi", "")
        if not item.get("stratum"):
            item["stratum"] = case.get("stratum", "")
        if not item.get("abstract_source_original"):
            item["abstract_source_original"] = case.get(
                "abstract_source_original", ""
            )
        prepared.append(item)
    return prepared


def load_calibration_records(results_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases = load_cases(results_dir)
    assessment_paths = sorted((results_dir / "assessments").glob("*.jsonl"))
    if not assessment_paths:
        raise RuntimeError(f"No assessment JSONL files found under {results_dir}")
    rows: list[dict[str, Any]] = []
    for path in assessment_paths:
        rows.extend(prepare_records(load_jsonl(path), cases, path.stem))
    return rows, cases


def load_microtest_records(path: Path) -> list[dict[str, Any]]:
    return prepare_records(load_jsonl(path), None, "microtest_v1")


def error_taxonomy(error: str) -> str:
    lowered = error.lower()
    if "requires evidence" in lowered:
        return "requires evidence"
    if "duplicate json key" in lowered:
        return "duplicate JSON key"
    if "quote" in lowered:
        return "quote/evidence grounding"
    if "coherence" in lowered or "requires i" in lowered:
        return "coherence"
    if "schema" in lowered:
        return "schema"
    if "order/coverage" in lowered:
        return "criterion order/coverage"
    if "fields are invalid" in lowered:
        return "field shape"
    if "status is invalid" in lowered:
        return "status"
    if "evidence must" in lowered or "evidence forbids" in lowered:
        return "evidence shape"
    if "reason" in lowered:
        return "reason"
    return "other validation"


def route_counts(rows: Iterable[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[str(row.get("phase1_route") or "technical_error")] += 1
    return counts


def route_table(rows: list[dict[str, Any]]) -> str:
    labels = ["all", "include", "exclude"]
    routes = ["include", "needs_manual", "invalid_assessment", "technical_error"]
    lines = ["| Label | Records | " + " | ".join(routes) + " |", "|---|---:|" + "---:|" * len(routes)]
    for label in labels:
        selected = rows if label == "all" else [r for r in rows if r["_label"] == label]
        counts = route_counts(selected)
        lines.append(
            "| "
            + label
            + " | "
            + str(len(selected))
            + " | "
            + " | ".join(str(counts[route]) for route in routes)
            + " |"
        )
    return "\n".join(lines)


def hard_fail_table(rows: list[dict[str, Any]], criterion_ids: list[str]) -> str:
    buckets: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows:
        label = row["_label"] if row["_label"] in {"include", "exclude"} else "other"
        validity = "valid" if row["_valid"] else "invalid"
        for criterion_id in row.get("hard_fails", []) or []:
            buckets[(criterion_id, label, validity)] += 1
    lines = [
        "| Criterion | include valid | include invalid | exclude valid | exclude invalid |",
        "|---|---:|---:|---:|---:|",
    ]
    for criterion_id in criterion_ids:
        lines.append(
            f"| {criterion_id} | "
            f"{buckets[(criterion_id, 'include', 'valid')]} | "
            f"{buckets[(criterion_id, 'include', 'invalid')]} | "
            f"{buckets[(criterion_id, 'exclude', 'valid')]} | "
            f"{buckets[(criterion_id, 'exclude', 'invalid')]} |"
        )
    return "\n".join(lines)


def evaluate_candidate_rules(
    calibration_rows: list[dict[str, Any]],
    microtest_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Apply Rules 1 and 2; Rule 1 is evaluated on calibration records.

    Rule 2 retains occurrence counters for reporting, but qualifies only on
    canonical DOI support across the union of calibration and micro-test rows.
    """

    results: dict[str, dict[str, Any]] = {}
    for criterion_id in CANDIDATE_CRITERIA:
        include_hits = [
            row
            for row in calibration_rows
            if row["_valid"]
            and row["_label"] == "include"
            and criterion_id in (row.get("hard_fails") or [])
        ]
        calibration_support = [
            row
            for row in calibration_rows
            if row["_valid"]
            and row["_label"] == "exclude"
            and criterion_id in (row.get("hard_fails") or [])
        ]
        microtest_support = [
            row
            for row in microtest_rows
            if row["_valid"]
            and row["_label"] == "exclude"
            and criterion_id in (row.get("hard_fails") or [])
        ]
        calibration_support_dois = {
            record_doi(row) for row in calibration_support if record_doi(row)
        }
        microtest_support_dois = {
            record_doi(row) for row in microtest_support if record_doi(row)
        }
        unique_doi_support = len(calibration_support_dois | microtest_support_dois)
        occurrence_support = len(calibration_support) + len(microtest_support)
        if include_hits:
            status = "disqualified"
            reason = "Rule 1: valid include record contains this hard-fail."
        elif unique_doi_support < 3:
            status = "not_qualified"
            reason = (
                f"Rule 2: only {unique_doi_support} unique DOI(s) support this "
                "hard-fail on valid exclude records; at least 3 required."
            )
        else:
            status = "qualified"
            reason = "Rules 1 and 2 passed."
        results[criterion_id] = {
            "criterion_id": criterion_id,
            "status": status,
            "reason": reason,
            "valid_include_hits": len(include_hits),
            "calibration_exclude_support": len(calibration_support),
            "microtest_exclude_support": len(microtest_support),
            "unique_doi_support": unique_doi_support,
            "exclude_support": occurrence_support,
            "include_hit_case_ids": [row.get("case_id") for row in include_hits],
        }
    return results


def sampling_key(row: dict[str, Any], criterion_id: str) -> str:
    value = f"{record_doi(row)}:{criterion_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def sample_rule3_instances(
    rows: list[dict[str, Any]],
    criterion_id: str,
    excluded_dois: set[str] | None = None,
    max_instances: int = 5,
) -> list[dict[str, Any]]:
    excluded = {canonical_doi(doi) for doi in (excluded_dois or set())}
    candidates = [
        row
        for row in rows
        if row["_valid"]
        and row["_label"] == "exclude"
        and criterion_id in (row.get("hard_fails") or [])
        and record_doi(row) not in excluded
        and not bool(row.get("in_microtest"))
    ]
    return sorted(
        candidates,
        key=lambda row: (sampling_key(row, criterion_id), str(row.get("case_id", ""))),
    )[:max_instances]


def criterion_row(row: dict[str, Any], criterion_id: str) -> dict[str, Any] | None:
    for item in row.get("full_assessment", []) or []:
        if isinstance(item, dict) and item.get("id") == criterion_id:
            return item
    return None


def phase2_checklist(
    samples: dict[str, list[dict[str, Any]]],
    cases: dict[str, dict[str, Any]],
    results_dir: Path,
) -> str:
    lines = [
        "# Phase 2 sample checklist — calibration Rule 3",
        "",
        f"Results directory: `{results_dir}`",
        "",
        "Human verification is required for every sampled hard-fail below. "
        "A single REFUSÉ removes the criterion from the allowlist until v2.",
        "",
        f"Sampling rule: {RULE_3_TEXT}",
        "",
    ]
    item_number = 0
    summary_rows: list[tuple[int, str, str]] = []
    for criterion_id in CANDIDATE_CRITERIA:
        criterion_samples = samples.get(criterion_id, [])
        if not criterion_samples:
            continue
        lines.extend([f"## {criterion_id}", ""])
        for row in criterion_samples:
            item_number += 1
            case = cases.get(str(row.get("case_id")), row.get("_case", {}))
            title = case.get("title", "")
            summary_rows.append((item_number, criterion_id, str(row.get("doi", ""))))
            assessment = criterion_row(row, criterion_id) or {}
            lines.extend(
                [
                    f"**{item_number}. {criterion_id} = {assessment.get('status', 'unknown')}**",
                    f"- Case: `{row.get('case_id', '')}`",
                    f"- DOI: `{row.get('doi', '')}`",
                    f"- Title: {title}",
                ]
            )
            evidence = assessment.get("evidence", []) or []
            for item in evidence:
                lines.append(
                    f"- Citation [{item.get('source', '')}] : « {item.get('quote', '')} »"
                )
            lines.extend(
                [
                    f"- Raison du modèle : {assessment.get('reason', '')}",
                    "- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :",
                    "",
                ]
            )
    if item_number == 0:
        lines.extend(["Aucun critère n'est encore qualifié pour l'échantillonnage.", ""])

    lines.extend(
        [
            "## Synthèse Phase 2",
            "",
            "| # | Critère | DOI | Verdict |",
            "|---|---|---|---|",
        ]
    )
    for number, criterion_id, doi in summary_rows:
        lines.append(f"| {number} | {criterion_id} | {doi} | À remplir |")
    if not summary_rows:
        lines.append("| — | — | — | À remplir |")
    lines.extend(
        [
            "",
            "### Résumé par critère",
            "",
            "| Critère | Échantillon | Confirmés | Refusés | Allowlist après vérification |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for criterion_id in CANDIDATE_CRITERIA:
        lines.append(f"| {criterion_id} | {len(samples.get(criterion_id, []))} |  |  |  |")
    return "\n".join(lines) + "\n"


def simulate_allowlist(
    rows: list[dict[str, Any]], qualified: set[str]
) -> dict[str, Any]:
    valid_exclude = [row for row in rows if row["_valid"] and row["_label"] == "exclude"]
    valid_include = [row for row in rows if row["_valid"] and row["_label"] == "include"]
    excluded = [
        row
        for row in valid_exclude
        if qualified.intersection(row.get("hard_fails") or [])
    ]
    include_false_excludes = [
        row
        for row in valid_include
        if qualified.intersection(row.get("hard_fails") or [])
    ]
    return {
        "qualified_criteria": sorted(qualified),
        "valid_exclude_records": len(valid_exclude),
        "auto_excluded_records": len(excluded),
        "automation_rate": (
            len(excluded) / len(valid_exclude) if valid_exclude else 0.0
        ),
        "valid_include_records": len(valid_include),
        "include_records_routed_exclude": len(include_false_excludes),
        "exclude_case_ids": [row.get("case_id") for row in excluded],
        "include_case_ids": [row.get("case_id") for row in include_false_excludes],
    }


def stratification_table(rows: list[dict[str, Any]], field: str) -> str:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(field, "") or "") or "(missing)"
        groups[value].append(row)
    lines = [
        f"| {field} | Records | Include | Exclude | Valid | Invalid | Include route | Manual route | Invalid route |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for value in sorted(groups):
        group = groups[value]
        counts = route_counts(group)
        lines.append(
            f"| {value} | {len(group)} | "
            f"{sum(row['_label'] == 'include' for row in group)} | "
            f"{sum(row['_label'] == 'exclude' for row in group)} | "
            f"{sum(row['_valid'] for row in group)} | "
            f"{sum(not row['_valid'] for row in group)} | "
            f"{counts['include']} | {counts['needs_manual']} | {counts['invalid_assessment']} |"
        )
    return "\n".join(lines)


def build_report(
    results_dir: Path,
    rows: list[dict[str, Any]],
    microtest_rows: list[dict[str, Any]],
    candidate_results: dict[str, dict[str, Any]],
    simulation: dict[str, Any],
    samples: dict[str, list[dict[str, Any]]],
) -> str:
    criterion_ids = sorted(
        {
            str(item.get("id"))
            for row in rows
            for item in row.get("full_assessment", []) or []
            if isinstance(item, dict) and item.get("id")
        }
        | set(CANDIDATE_CRITERIA)
        | {"I2_REPRODUCIBLE", "E3_BENCHMARK_ONLY"}
    )
    invalid_rows = [row for row in rows if not row["_valid"]]
    invalid_rate = len(invalid_rows) / len(rows) if rows else 0.0
    taxonomy: Counter[str] = Counter()
    for row in rows:
        for error in row.get("validation_errors", []) or []:
            taxonomy[error_taxonomy(str(error))] += 1
        for error in row.get("coherence_errors", []) or []:
            taxonomy[error_taxonomy(str(error))] += 1
    include_invalid_hardfails = [
        row
        for row in invalid_rows
        if row["_label"] == "include"
    ]
    alert_counts: Counter[str] = Counter()
    alert_case_ids: dict[str, list[str]] = defaultdict(list)
    for row in include_invalid_hardfails:
        for criterion_id in row.get("hard_fails", []) or []:
            if criterion_id in CANDIDATE_CRITERIA:
                alert_counts[criterion_id] += 1
                alert_case_ids[criterion_id].append(str(row.get("case_id")))

    lines = [
        "# Calibration report — criteria-matrix v1",
        "",
        f"Results directory: `{results_dir}`",
        "",
        "This report is offline-only. It does not call an API and does not alter the frozen v1 harness.",
        "",
        "## Route distribution",
        "",
        route_table(rows),
        "",
        "## Invalid assessments and error taxonomy",
        "",
        f"Invalid assessments: {len(invalid_rows)}/{len(rows)} ({invalid_rate:.1%}).",
        "",
        "| Error class | Count |",
        "|---|---:|",
    ]
    for category, count in sorted(taxonomy.items()):
        lines.append(f"| {category} | {count} |")
    lines.extend(
        [
            "",
            "The `requires evidence` count is reported separately because it is a registered v2 input.",
            "",
            "## Hard-fails by criterion and label",
            "",
            hard_fail_table(rows, criterion_ids),
            "",
            "## Candidate criteria: Rules 1 and 2",
            "",
            f"{RULE_1_TEXT}",
            "",
            f"{RULE_2_TEXT}",
            "",
            "| Criterion | Status | Valid include hits | Calibration exclude support (occurrences) | Micro-test exclude support (occurrences) | Unique DOI support | Total support (occurrences) | Reason |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for criterion_id in CANDIDATE_CRITERIA:
        result = candidate_results[criterion_id]
        lines.append(
            f"| {criterion_id} | {result['status']} | {result['valid_include_hits']} | "
            f"{result['calibration_exclude_support']} | {result['microtest_exclude_support']} | "
            f"{result['unique_doi_support']} | {result['exclude_support']} | {result['reason']} |"
        )
    lines.extend(
        [
            "",
            "Blocked regardless of measurement: `I2_REPRODUCIBLE` and `E3_BENCHMARK_ONLY`.",
            "",
            "## Rule 3 sampling",
            "",
            f"{RULE_3_TEXT}",
            "",
            "| Criterion | Qualified for sampling | Sample size | Case IDs |",
            "|---|---|---:|---|",
        ]
    )
    for criterion_id in CANDIDATE_CRITERIA:
        result = candidate_results[criterion_id]
        sample = samples.get(criterion_id, [])
        lines.append(
            f"| {criterion_id} | {result['status'] == 'qualified'} | {len(sample)} | "
            f"{', '.join(str(row.get('case_id')) for row in sample)} |"
        )
    lines.extend(
        [
            "",
            "The generated `phase2_sample_checklist.md` contains the empty human-verdict fields.",
            "",
            "## Allowlist simulation",
            "",
            f"Simulated allowlist: {', '.join(simulation['qualified_criteria']) or '(empty)'}.",
            f"Valid exclude records routed `exclude`: {simulation['auto_excluded_records']}/{simulation['valid_exclude_records']} ({simulation['automation_rate']:.1%}).",
            f"Valid include records routed `exclude`: {simulation['include_records_routed_exclude']}/{simulation['valid_include_records']}.",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Valid exclude records | {simulation['valid_exclude_records']} |",
            f"| Auto-excluded exclude records | {simulation['auto_excluded_records']} |",
            f"| Automation rate | {simulation['automation_rate']:.1%} |",
            f"| Include records auto-excluded | {simulation['include_records_routed_exclude']} |",
            "",
            "## Signal d'alerte",
            "",
            "Hard-fails on include records with invalid assessments are reported but do not disqualify a criterion:",
            "",
            "| Criterion | Count | Case IDs |",
            "|---|---:|---|",
        ]
    )
    for criterion_id in CANDIDATE_CRITERIA:
        lines.append(
            f"| {criterion_id} | {alert_counts[criterion_id]} | "
            f"{', '.join(alert_case_ids[criterion_id])} |"
        )
    lines.extend(
        [
            "",
            "## Stratification",
            "",
            "### By stratum",
            "",
            stratification_table(rows, "stratum"),
            "",
            "### By abstract source",
            "",
            stratification_table(rows, "abstract_source_original"),
            "",
            "## Frozen rules",
            "",
            "I2 and E3 remain excluded from any auto_excludable allowlist, and no prompt, criteria, matcher, or rule was changed after observation.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(
    results_dir: Path,
    microtest_assessments: Path = DEFAULT_MICROTEST_ASSESSMENTS,
) -> dict[str, Any]:
    calibration_rows, cases = load_calibration_records(results_dir)
    microtest_rows = load_microtest_records(microtest_assessments)
    candidate_results = evaluate_candidate_rules(calibration_rows, microtest_rows)
    qualified = {
        criterion_id
        for criterion_id, result in candidate_results.items()
        if result["status"] == "qualified"
    }
    simulation = simulate_allowlist(calibration_rows, qualified)
    excluded_dois = microtest_dois()
    samples = {
        criterion_id: sample_rule3_instances(
            calibration_rows, criterion_id, excluded_dois
        )
        for criterion_id in CANDIDATE_CRITERIA
        if criterion_id in qualified
    }
    checklist_path = results_dir / "phase2_sample_checklist.md"
    checklist_path.write_text(
        phase2_checklist(samples, cases, results_dir), encoding="utf-8"
    )
    report_path = results_dir / "calibration_report.md"
    report_path.write_text(
        build_report(
            results_dir,
            calibration_rows,
            microtest_rows,
            candidate_results,
            simulation,
            samples,
        ),
        encoding="utf-8",
    )
    return {
        "report_path": report_path,
        "checklist_path": checklist_path,
        "candidate_results": candidate_results,
        "simulation": simulation,
        "sample_counts": {
            criterion_id: len(items) for criterion_id, items in samples.items()
        },
    }


if __name__ == "__main__":
    try:
        args = parse_args()
        result = analyze(args.results_dir, args.microtest_assessments)
        print(f"REPORT={result['report_path']}")
        print(f"CHECKLIST={result['checklist_path']}")
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
