#!/usr/bin/env python3
"""Offline evaluation of a completed criteria-matrix v2 micro-test."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True
V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR))

from run_microtest_v2 import (  # noqa: E402
    BLOCK_C_IDS,
    CASE_SPECS,
    SUCCESS_CRITERIA,
    canonical_doi,
    load_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    return parser.parse_args()


def assessment_is_valid(row: dict[str, Any]) -> bool:
    return (
        "technical_error" not in row
        and row.get("validation_errors") == []
        and row.get("coherence_errors") == []
    )


def record_label(row: dict[str, Any]) -> str:
    return str(row.get("human_label", "") or "").strip().lower()


def prepare_rows(
    rows: Iterable[dict[str, Any]], cases: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        case = cases.get(str(row.get("case_id", "")), {})
        item["_case"] = case
        item["_valid"] = assessment_is_valid(row)
        item["_label"] = record_label(row) or str(case.get("human_label", "")).lower()
        item["_bloc"] = str(row.get("bloc") or case.get("bloc") or "")
        item["_replicate"] = str(row.get("replicate") or "")
        if not item.get("doi"):
            item["doi"] = case.get("doi", "")
        prepared.append(item)
    return prepared


def load_records(results_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cases_path = results_dir / "cases.jsonl"
    if not cases_path.is_file():
        raise RuntimeError(f"cases.jsonl is missing: {cases_path}")
    cases = {row["case_id"]: row for row in load_jsonl(cases_path)}
    assessment_paths = sorted((results_dir / "assessments").glob("*.jsonl"))
    if not assessment_paths:
        raise RuntimeError(f"No assessment JSONL found under {results_dir}")
    rows: list[dict[str, Any]] = []
    for path in assessment_paths:
        rows.extend(prepare_rows(load_jsonl(path), cases))
    return rows, cases


def error_taxonomy(error: str) -> str:
    lowered = error.lower()
    if "requires evidence" in lowered:
        return "requires evidence"
    if "coherence" in lowered or "requires i" in lowered:
        return "coherence"
    if "quote" in lowered or "evidence" in lowered:
        return "quote/evidence grounding"
    if "schema" in lowered:
        return "schema"
    if "order/coverage" in lowered:
        return "criterion order/coverage"
    if "status is invalid" in lowered:
        return "status"
    if "fields are invalid" in lowered:
        return "field shape"
    if "reason" in lowered:
        return "reason"
    return "other validation"


def all_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(str(error) for error in row.get("validation_errors", []) or [])
    errors.extend(str(error) for error in row.get("coherence_errors", []) or [])
    return errors


def route_counts(rows: Iterable[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[str(row.get("phase1_route") or "technical_error")] += 1
    return counts


def invalid_rate_table(rows: list[dict[str, Any]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["_bloc"]), str(row["_replicate"]))].append(row)
    lines = [
        "| Bloc | Réplicat | Records | Invalides | Taux |",
        "|---|---:|---:|---:|---:|",
    ]
    for (bloc, replicate), group in sorted(groups.items()):
        invalid = sum(not row["_valid"] for row in group)
        rate = invalid / len(group) if group else 0.0
        lines.append(f"| {bloc} | {replicate} | {len(group)} | {invalid} | {rate:.1%} |")
    invalid = sum(not row["_valid"] for row in rows)
    rate = invalid / len(rows) if rows else 0.0
    lines.append(f"| ALL | — | {len(rows)} | {invalid} | {rate:.1%} |")
    return "\n".join(lines)


def oracle_map() -> dict[str, dict[str, Any]]:
    return {spec["case_id"]: spec for spec in CASE_SPECS}


def evaluate_block_a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    oracle = oracle_map()
    fp_cases = [spec for spec in CASE_SPECS if str(spec["category"]).startswith("known_reasoner_false_positive")]
    by_replicate: dict[str, dict[str, Any]] = {}
    for replicate in sorted({str(row["_replicate"]) for row in rows if row["_bloc"] == "A"}):
        selected = {
            row["case_id"]: row
            for row in rows
            if row["_bloc"] == "A" and str(row["_replicate"]) == replicate
        }
        oracle_hits = 0
        oracle_missing: list[str] = []
        for spec in fp_cases:
            row = selected.get(spec["case_id"])
            expected = {spec["expected_primary"], *spec["accepted_alternatives"]}
            if row and row["_valid"] and expected.intersection(row.get("hard_fails", []) or []):
                oracle_hits += 1
            else:
                oracle_missing.append(spec["case_id"])
        include_false = [
            row["case_id"]
            for row in selected.values()
            if row["_valid"] and row["_label"] == "include" and row.get("hard_fails")
        ]
        exclude_routed_include = [
            row["case_id"]
            for row in selected.values()
            if row["_valid"] and row["_label"] == "exclude" and row.get("phase1_route") == "include"
        ]
        by_replicate[replicate] = {
            "oracle_hits": oracle_hits,
            "oracle_total": len(fp_cases),
            "oracle_pass": oracle_hits >= 2,
            "oracle_missing": oracle_missing,
            "include_false_hard_fails": include_false,
            "exclude_routed_include": exclude_routed_include,
        }
    return by_replicate


def evaluate_block_c(rows: list[dict[str, Any]]) -> dict[str, Any]:
    e4_ids = [case_id for case_id in BLOCK_C_IDS if case_id != "gold_031"]
    e4_rows = [row for row in rows if row["_bloc"] == "C" and row["case_id"] in e4_ids]
    i4_rows = [row for row in rows if row["_bloc"] == "C" and row["case_id"] == "gold_031"]
    e4_violations = [
        row["case_id"]
        for row in e4_rows
        if not row["_valid"] or "E4_APPLICATION_WITHOUT_PROMPT_DETAIL" in (row.get("hard_fails") or [])
    ]
    i4_violations = [
        row["case_id"]
        for row in i4_rows
        if not row["_valid"] or "I4_PRACTITIONER" in (row.get("hard_fails") or [])
    ]
    return {
        "e4_cases": len(e4_ids),
        "e4_records": len(e4_rows),
        "e4_violations": e4_violations,
        "i4_records": len(i4_rows),
        "i4_violations": i4_violations,
        "pass": not e4_violations and not i4_violations and len(e4_rows) == 10 and len(i4_rows) == 2,
    }


def evaluate_stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("model", "")), str(row["case_id"]))].append(row)
    identical = 0
    comparable = 0
    incomplete: list[str] = []
    for key, group in sorted(grouped.items()):
        if len(group) != 2:
            incomplete.append(f"{key[0]}/{key[1]}")
            continue
        comparable += 1
        hard_fail_sets = [frozenset(row.get("hard_fails") or []) for row in group]
        if hard_fail_sets[0] == hard_fail_sets[1]:
            identical += 1
    total_case_model_pairs = len(grouped)
    rate = identical / comparable if comparable else 0.0
    return {
        "identical_pairs": identical,
        "comparable_pairs": comparable,
        "total_case_model_pairs": total_case_model_pairs,
        "identical_rate": rate,
        "incomplete_pairs": incomplete,
        "pass": rate >= 0.90 and not incomplete,
    }


def evaluate_v2(rows: list[dict[str, Any]]) -> dict[str, Any]:
    taxonomy: Counter[str] = Counter()
    requires_evidence = 0
    for row in rows:
        for error in all_errors(row):
            category = error_taxonomy(error)
            taxonomy[category] += 1
            if category == "requires evidence":
                requires_evidence += 1
    invalid = sum(not row["_valid"] for row in rows)
    invalid_rate = invalid / len(rows) if rows else 0.0
    block_a = evaluate_block_a(rows)
    block_c = evaluate_block_c(rows)
    include_false = [
        f"{row.get('bloc')}/{row.get('case_id')}/r{row.get('replicate')}"
        for row in rows
        if row["_valid"] and row["_label"] == "include" and row.get("hard_fails")
    ]
    stability = evaluate_stability(rows)
    a = {
        "status": "PASS" if requires_evidence == 0 else "FAIL",
        "requires_evidence_errors": requires_evidence,
        "records": len(rows),
    }
    b = {
        "status": "PASS" if invalid_rate <= 0.10 else "FAIL",
        "invalid": invalid,
        "total": len(rows),
        "rate": invalid_rate,
        "threshold": 0.10,
    }
    c = {
        "status": "PASS"
        if block_a and all(
            item["oracle_pass"]
            and not item["include_false_hard_fails"]
            and not item["exclude_routed_include"]
            for item in block_a.values()
        )
        else "FAIL",
        "by_replicate": block_a,
    }
    d = {"status": "PASS" if block_c["pass"] else "FAIL", **block_c}
    e = {
        "status": "PASS" if not include_false else "FAIL",
        "include_false_hard_fails": include_false,
    }
    f = {"status": "PASS" if stability["pass"] else "FAIL", **stability}
    return {
        "criteria": {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f},
        "taxonomy": taxonomy,
        "invalid_rate_table": invalid_rate_table(rows),
        "overall_verdict": "v2 falsified"
        if any(a["status"] == "FAIL" for a in (a, b, c, d, e))
        else "v2 not falsified",
    }


def render_report(
    results_dir: Path, rows: list[dict[str, Any]], cases: dict[str, dict[str, Any]], evaluation: dict[str, Any]
) -> str:
    criteria_results = evaluation["criteria"]
    lines = [
        "# criteria-matrix v2 micro-test report",
        "",
        f"Results directory: `{results_dir}`",
        "",
        f"## Overall verdict: **{evaluation['overall_verdict']}**",
        "",
        "A failure of (a)–(e) falsifies v2. A failure of (f) does not falsify v2, but makes replicate reproduction mandatory before any auto-exclusion.",
        "",
        "## Criteria (a)–(f)",
        "",
        "| Criterion | Status | Numbers / reason |",
        "|---|---|---|",
    ]
    for criterion in SUCCESS_CRITERIA:
        result = criteria_results[criterion["id"]]
        if criterion["id"] == "a":
            numbers = f"{result['requires_evidence_errors']} requires-evidence errors across {result['records']} records."
        elif criterion["id"] == "b":
            numbers = f"{result['invalid']}/{result['total']} invalid ({result['rate']:.1%}); threshold ≤10%."
        elif criterion["id"] == "c":
            numbers = "; ".join(
                f"r{rep}: oracle {data['oracle_hits']}/{data['oracle_total']}, include false {len(data['include_false_hard_fails'])}, exclude→include {len(data['exclude_routed_include'])}"
                for rep, data in sorted(result["by_replicate"].items())
            ) or "no block-A replicate records"
        elif criterion["id"] == "d":
            numbers = f"E4 violations={len(result['e4_violations'])}; I4 violations={len(result['i4_violations'])}; E4 records={result['e4_records']}/10, I4 records={result['i4_records']}/2."
        elif criterion["id"] == "e":
            numbers = f"{len(result['include_false_hard_fails'])} valid include records with hard-fails."
        else:
            numbers = f"{result['identical_pairs']}/{result['comparable_pairs']} comparable pairs identical ({result['identical_rate']:.1%}); incomplete={len(result['incomplete_pairs'])}."
        lines.append(f"| ({criterion['id']}) | **{result['status']}** | {numbers} |")
    lines.extend(
        [
            "",
            "## Invalid assessments by block and replicate",
            "",
            evaluation["invalid_rate_table"],
            "",
            "## Error taxonomy",
            "",
            "The registered `requires evidence` category is listed first.",
            "",
            "| Error class | Count |",
            "|---|---:|",
        ]
    )
    taxonomy: Counter[str] = evaluation["taxonomy"]
    for category in sorted(taxonomy, key=lambda key: (key != "requires evidence", key)):
        lines.append(f"| {category} | {taxonomy[category]} |")
    lines.extend(["", "## Block A non-regression against v1 oracles", ""])
    lines.extend(
        [
            "| Replicate | Oracle hits | FP total | Oracle criterion (b) | Valid include hard-fails | Exclude routed include |",
            "|---:|---:|---:|---|---:|---:|",
        ]
    )
    for replicate, data in sorted(criteria_results["c"]["by_replicate"].items()):
        lines.append(
            f"| {replicate} | {data['oracle_hits']} | {data['oracle_total']} | {'PASS' if data['oracle_pass'] else 'FAIL'} | {len(data['include_false_hard_fails'])} | {len(data['exclude_routed_include'])} |"
        )
    lines.extend(
        [
            "",
            "## Block C E4/I4 hard-fail checks",
            "",
            f"E4 target cases: {', '.join([case_id for case_id in BLOCK_C_IDS if case_id != 'gold_031'])}; violations: {', '.join(criteria_results['d']['e4_violations']) or 'none'}.",
            f"I4 target case: gold_031; violations: {', '.join(criteria_results['d']['i4_violations']) or 'none'}.",
            "",
            "## Include hard-fail safety check",
            "",
            f"Valid include records with hard-fails: {', '.join(criteria_results['e']['include_false_hard_fails']) or 'none'}.",
            "",
            "## Inter-replicate stability",
            "",
            f"{criteria_results['f']['identical_pairs']}/{criteria_results['f']['comparable_pairs']} comparable case/model pairs have identical hard-fail sets ({criteria_results['f']['identical_rate']:.1%}); incomplete pairs: {', '.join(criteria_results['f']['incomplete_pairs']) or 'none'}.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def analyze(results_dir: Path) -> dict[str, Any]:
    rows, cases = load_records(results_dir)
    evaluation = evaluate_v2(rows)
    report_path = results_dir / "v2_report.md"
    report_path.write_text(render_report(results_dir, rows, cases, evaluation), encoding="utf-8")
    return {"report_path": report_path, "evaluation": evaluation}


if __name__ == "__main__":
    try:
        args = parse_args()
        result = analyze(args.results_dir)
        print(f"REPORT={result['report_path']}")
        print(f"VERDICT={result['evaluation']['overall_verdict']}")
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
