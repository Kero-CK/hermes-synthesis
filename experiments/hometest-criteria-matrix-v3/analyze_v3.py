#!/usr/bin/env python3
"""Offline evaluation of a completed criteria-matrix v3 micro-test."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True
V3_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V3_DIR))

from run_microtest_v3 import (  # noqa: E402
    BLOCK_C_IDS,
    CASE_SPECS,
    E4_TARGET_IDS,
    I4_TARGET_IDS,
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


def load_records(
    results_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
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
    if "quote found in " in lowered and "declared " in lowered:
        return "source-label mismatch"
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
        lines.append(
            f"| {bloc} | {replicate} | {len(group)} | {invalid} | {rate:.1%} |"
        )
    invalid = sum(not row["_valid"] for row in rows)
    rate = invalid / len(rows) if rows else 0.0
    lines.append(f"| ALL | — | {len(rows)} | {invalid} | {rate:.1%} |")
    return "\n".join(lines)


def oracle_map() -> dict[str, dict[str, Any]]:
    return {spec["case_id"]: spec for spec in CASE_SPECS}


def evaluate_block_a(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fp_cases = [
        spec
        for spec in CASE_SPECS
        if str(spec["category"]).startswith("known_reasoner_false_positive")
    ]
    by_replicate: dict[str, dict[str, Any]] = {}
    for replicate in sorted(
        {str(row["_replicate"]) for row in rows if row["_bloc"] == "A"}
    ):
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
            if row["_valid"]
            and row["_label"] == "exclude"
            and row.get("phase1_route") == "include"
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


def reproduced_hard_fails(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], set[str]]:
    """Return hard-fails present in both valid replicates of each case/model."""

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("model", "")), str(row["case_id"]))].append(row)
    result: dict[tuple[str, str], set[str]] = {}
    for key, group in groups.items():
        if len(group) != 2 or any(not row["_valid"] for row in group):
            result[key] = set()
            continue
        result[key] = set(group[0].get("hard_fails") or []).intersection(
            group[1].get("hard_fails") or []
        )
    return result


def stability_by_block(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("model", "")), row["_bloc"], row["case_id"])].append(row)
    by_block: dict[str, dict[str, Any]] = {}
    for block in sorted({row["_bloc"] for row in rows}):
        selected = [group for key, group in groups.items() if key[1] == block]
        comparable = sum(len(group) == 2 for group in selected)
        identical = 0
        incomplete: list[str] = []
        for group in selected:
            if len(group) != 2:
                incomplete.append(str(group[0].get("case_id", "unknown")))
                continue
            if set(group[0].get("hard_fails") or []) == set(
                group[1].get("hard_fails") or []
            ):
                identical += 1
        by_block[block] = {
            "identical": identical,
            "comparable": comparable,
            "rate": identical / comparable if comparable else 0.0,
            "incomplete": incomplete,
        }
    return by_block


def target_reproduction_violations(
    reproduced: dict[tuple[str, str], set[str]],
    target_ids: list[str],
    criterion_id: str,
) -> list[str]:
    violations: list[str] = []
    for case_id in target_ids:
        matches = [
            (model, identifier, hard_fails)
            for (model, identifier), hard_fails in reproduced.items()
            if identifier == case_id
        ]
        if not matches:
            violations.append(f"{case_id}:missing")
            continue
        for model, _identifier, hard_fails in matches:
            if criterion_id in hard_fails:
                violations.append(f"{model}/{case_id}")
    return violations


def reproduced_include_false_hard_fails(
    rows: list[dict[str, Any]], reproduced: dict[tuple[str, str], set[str]]
) -> list[str]:
    labels: dict[tuple[str, str], str] = {}
    for row in rows:
        labels[(str(row.get("model", "")), row["case_id"])] = row["_label"]
    return [
        f"{model}/{case_id}"
        for (model, case_id), hard_fails in sorted(reproduced.items())
        if labels.get((model, case_id)) == "include" and hard_fails
    ]


def evaluate_v3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    taxonomy: Counter[str] = Counter()
    requires_evidence = 0
    source_label_mismatches = 0
    for row in rows:
        for error in all_errors(row):
            category = error_taxonomy(error)
            taxonomy[category] += 1
            if category == "requires evidence":
                requires_evidence += 1
            if category == "source-label mismatch":
                source_label_mismatches += 1

    invalid = sum(not row["_valid"] for row in rows)
    invalid_rate = invalid / len(rows) if rows else 0.0
    block_a = evaluate_block_a(rows)
    reproduced = reproduced_hard_fails(rows)
    e4_violations = target_reproduction_violations(
        reproduced, E4_TARGET_IDS, "E4_APPLICATION_WITHOUT_PROMPT_DETAIL"
    )
    i4_violations = target_reproduction_violations(
        reproduced, I4_TARGET_IDS, "I4_PRACTITIONER"
    )
    include_false = reproduced_include_false_hard_fails(rows, reproduced)
    stability = stability_by_block(rows)

    a = {
        "status": "PASS" if requires_evidence == 0 else "FAIL",
        "requires_evidence_errors": requires_evidence,
        "records": len(rows),
    }
    b = {
        "status": "PASS" if source_label_mismatches == 0 else "FAIL",
        "source_label_mismatches": source_label_mismatches,
        "records": len(rows),
    }
    c = {
        "status": "PASS" if invalid_rate <= 0.10 else "FAIL",
        "invalid": invalid,
        "total": len(rows),
        "rate": invalid_rate,
        "threshold": 0.10,
    }
    d = {
        "status": "PASS"
        if block_a
        and all(
            item["oracle_pass"]
            and not item["include_false_hard_fails"]
            and not item["exclude_routed_include"]
            for item in block_a.values()
        )
        else "FAIL",
        "by_replicate": block_a,
    }
    e = {
        "status": "PASS" if not e4_violations and not i4_violations else "FAIL",
        "e4_violations": e4_violations,
        "i4_violations": i4_violations,
        "e4_targets": E4_TARGET_IDS,
        "i4_targets": I4_TARGET_IDS,
    }
    f = {
        "status": "PASS" if not include_false else "FAIL",
        "include_false_reproduced_hard_fails": include_false,
    }
    g = {
        "status": "PASS",
        "by_block": stability,
        "threshold": None,
    }
    falsifying = (a, b, c, d, e, f)
    return {
        "criteria": {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f, "g": g},
        "taxonomy": taxonomy,
        "reproduced_hard_fails": reproduced,
        "invalid_rate_table": invalid_rate_table(rows),
        "overall_verdict": "v3 falsified"
        if any(item["status"] == "FAIL" for item in falsifying)
        else "v3 not falsified",
    }


def render_report(
    results_dir: Path,
    rows: list[dict[str, Any]],
    cases: dict[str, dict[str, Any]],
    evaluation: dict[str, Any],
) -> str:
    del cases
    criteria_results = evaluation["criteria"]
    lines = [
        "# criteria-matrix v3 micro-test report",
        "",
        f"VERDICT={evaluation['overall_verdict']}",
        "",
        f"Results directory: `{results_dir}`",
        "",
        "## Critères (a)–(g)",
        "",
        "| Criterion | Status | Numbers / reason |",
        "|---|---|---|",
    ]
    for criterion in SUCCESS_CRITERIA:
        criterion_id = criterion["id"]
        result = criteria_results[criterion_id]
        if criterion_id == "a":
            numbers = f"{result['requires_evidence_errors']} requires-evidence errors / {result['records']} records."
        elif criterion_id == "b":
            numbers = f"{result['source_label_mismatches']} source-label mismatch errors / {result['records']} records."
        elif criterion_id == "c":
            numbers = f"{result['invalid']}/{result['total']} invalid ({result['rate']:.1%}); threshold ≤10%."
        elif criterion_id == "d":
            numbers = "; ".join(
                f"r{rep}: oracle {data['oracle_hits']}/{data['oracle_total']}, include false {len(data['include_false_hard_fails'])}, exclude→include {len(data['exclude_routed_include'])}"
                for rep, data in sorted(result["by_replicate"].items())
            ) or "no block-A replicate records"
        elif criterion_id == "e":
            numbers = f"E4 reproduced violations={len(result['e4_violations'])}; I4 reproduced violations={len(result['i4_violations'])}."
        elif criterion_id == "f":
            numbers = f"{len(result['include_false_reproduced_hard_fails'])} reproduced include hard-fail cases."
        else:
            numbers = "; ".join(
                f"{block}: {data['identical']}/{data['comparable']} identical ({data['rate']:.1%})"
                for block, data in sorted(result["by_block"].items())
            ) or "no block records"
        lines.append(f"| ({criterion_id}) | **{result['status']}** | {numbers} |")

    lines.extend(
        [
            "",
            "## Invalid assessments by block and replicate",
            "",
            evaluation["invalid_rate_table"],
            "",
            "## Error taxonomy",
            "",
            "The registered source-label mismatch class is listed first.",
            "",
            "| Error class | Count |",
            "|---|---:|",
        ]
    )
    taxonomy: Counter[str] = evaluation["taxonomy"]
    for category in sorted(
        taxonomy, key=lambda key: (key != "source-label mismatch", key)
    ):
        lines.append(f"| {category} | {taxonomy[category]} |")

    lines.extend(["", "## Block A non-regression against v1 oracles", ""])
    lines.extend(
        [
            "| Replicate | Oracle hits | FP total | Oracle pass | Valid include hard-fails | Exclude routed include |",
            "|---:|---:|---:|---|---:|---:|",
        ]
    )
    for replicate, data in sorted(criteria_results["d"]["by_replicate"].items()):
        lines.append(
            f"| {replicate} | {data['oracle_hits']} | {data['oracle_total']} | {'PASS' if data['oracle_pass'] else 'FAIL'} | {len(data['include_false_hard_fails'])} | {len(data['exclude_routed_include'])} |"
        )

    lines.extend(
        [
            "",
            "## Reproduced hard-fail parasite checks",
            "",
            f"E4 targets: {', '.join(E4_TARGET_IDS)}; reproduced violations: {', '.join(criteria_results['e']['e4_violations']) or 'none'}.",
            f"I4 targets: {', '.join(I4_TARGET_IDS)}; reproduced violations: {', '.join(criteria_results['e']['i4_violations']) or 'none'}.",
            "",
            "## Reproduced include safety",
            "",
            f"Reproduced hard-fails on valid include cases: {', '.join(criteria_results['f']['include_false_reproduced_hard_fails']) or 'none'}.",
            "",
            "## Stability by block",
            "",
        ]
    )
    for block, data in sorted(criteria_results["g"]["by_block"].items()):
        lines.append(
            f"- Bloc {block}: {data['identical']}/{data['comparable']} pairs identical ({data['rate']:.1%}); incomplete={len(data['incomplete'])}."
        )
    lines.append("")
    return "\n".join(lines)


def analyze(results_dir: Path) -> dict[str, Any]:
    rows, cases = load_records(results_dir)
    evaluation = evaluate_v3(rows)
    report_path = results_dir / "v3_report.md"
    report_path.write_text(
        render_report(results_dir, rows, cases, evaluation), encoding="utf-8"
    )
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
