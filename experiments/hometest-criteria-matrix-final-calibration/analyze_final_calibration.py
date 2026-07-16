#!/usr/bin/env python3
"""Offline analysis and assisted-policy simulation for terminal calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True

FINAL_DIR = Path(__file__).resolve().parent
V3_REPORT_PATH = (
    FINAL_DIR.parent
    / "hometest-criteria-matrix-v3"
    / "results"
    / "20260716T150859285210Z"
    / "v3_report.md"
)
I1_CRITERION = "I1_PROMPT_TECHNIQUE"
RULE3_MAX_SAMPLE = 5
ALLOWED_ALLOWLISTS = (frozenset(), frozenset({I1_CRITERION}))
TAXONOMY_ORDER = [
    "requires-evidence",
    "source-label mismatch",
    "grounding",
    "coherence",
    "technical",
    "schema",
    "other validation",
]

sys.path.insert(0, str(FINAL_DIR))
from run_final_calibration import (  # noqa: E402
    EXPECTED_CORPUS_SHA256,
    EXPECTED_CRITERIA_SHA256,
    EXPECTED_V3_PROMPT_SHA256,
    N_REPLICATES,
    POLICY_ALLOWLIST,
    check_final_integrity,
    load_jsonl,
)


class PolicyError(ValueError):
    """An allowlist outside the terminal I1-only policy was requested."""


class OfflineIntegrityError(RuntimeError):
    """The completed-results directory is not the frozen 40×2 contract."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def assessment_is_valid(row: dict[str, Any]) -> bool:
    return (
        "technical_error" not in row
        and row.get("validation_errors") == []
        and row.get("coherence_errors") == []
    )


def record_label(row: dict[str, Any], case: dict[str, Any]) -> str:
    return str(row.get("human_label") or case.get("human_label") or "").strip().lower()


def prepare_rows(
    rows: Iterable[dict[str, Any]], cases: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        case = cases.get(str(row.get("case_id", "")), {})
        item["_case"] = case
        item["_valid"] = assessment_is_valid(row)
        item["_label"] = record_label(row, case)
        item["_replicate"] = str(row.get("replicate", ""))
        item["_model"] = str(row.get("model", ""))
        if not item.get("doi"):
            item["doi"] = case.get("doi", "")
        prepared.append(item)
    return prepared


def load_records(
    results_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    integrity = verify_results_integrity(results_dir)
    return integrity["rows"], integrity["cases"], integrity["manifest"]


def verify_results_integrity(results_dir: Path) -> dict[str, Any]:
    """Fail loudly before report/checklist generation if any frozen gate fails."""

    cases_path = results_dir / "cases.jsonl"
    manifest_path = results_dir / "run_manifest.json"
    if not cases_path.is_file():
        raise OfflineIntegrityError(f"cases.jsonl is missing: {cases_path}")
    if not manifest_path.is_file():
        raise OfflineIntegrityError(f"run_manifest.json is missing: {manifest_path}")

    try:
        frozen = check_final_integrity(corpus_path=cases_path)
    except Exception as exc:
        raise OfflineIntegrityError(f"frozen source integrity failed: {exc}") from exc

    frozen_bytes = frozen["corpus_bytes"]
    result_bytes = cases_path.read_bytes()
    if result_bytes != frozen_bytes:
        raise OfflineIntegrityError("results cases.jsonl is not byte-identical to the frozen corpus")
    cases_rows = load_jsonl(cases_path)
    expected_case_ids = [str(case["case_id"]) for case in cases_rows]
    expected_ids = set(expected_case_ids)
    if len(cases_rows) != 40 or len(expected_ids) != 40:
        raise OfflineIntegrityError(
            f"expected exactly 40 unique cases, got {len(cases_rows)} rows / {len(expected_ids)} IDs"
        )
    cases = {row["case_id"]: row for row in cases_rows}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_manifest_values = {
        "prompt_sha256": EXPECTED_V3_PROMPT_SHA256,
        "criteria_sha256": EXPECTED_CRITERIA_SHA256,
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "requested_model": "deepseek-reasoner",
        "case_count": 40,
        "n_replicates": 2,
        "call_count": 80,
        "expected_call_slots": 80,
        "terminal_calibration": True,
        "prompt_optimization_closed": True,
    }
    for field, expected in required_manifest_values.items():
        if manifest.get(field) != expected:
            raise OfflineIntegrityError(
                f"manifest {field} mismatch: expected {expected!r}, got {manifest.get(field)!r}"
            )
    if not isinstance(manifest.get("response_models"), list):
        raise OfflineIntegrityError("manifest response_models must be a list")

    assessment_paths = sorted((results_dir / "assessments").glob("*.jsonl"))
    if not assessment_paths:
        raise OfflineIntegrityError(f"No assessment JSONL files found under {results_dir}")
    raw_rows = [
        row
        for path in assessment_paths
        for row in load_jsonl(path)
    ]
    if len(raw_rows) != 80:
        raise OfflineIntegrityError(f"expected exactly 80 assessment lines, got {len(raw_rows)}")

    seen_pairs: set[tuple[str, str]] = set()
    for row in raw_rows:
        case_id = str(row.get("case_id", ""))
        replicate = str(row.get("replicate", ""))
        if case_id not in expected_ids:
            raise OfflineIntegrityError(f"foreign or missing case_id in assessment: {case_id!r}")
        if replicate not in {"1", "2"}:
            raise OfflineIntegrityError(
                f"invalid replicate for {case_id}: {row.get('replicate')!r}"
            )
        pair = (case_id, replicate)
        if pair in seen_pairs:
            raise OfflineIntegrityError(f"duplicate assessment pair: {case_id}/r{replicate}")
        seen_pairs.add(pair)
        if str(row.get("model", "")) != manifest["requested_model"]:
            raise OfflineIntegrityError(
                f"assessment model mismatch for {case_id}/r{replicate}: "
                f"expected {manifest['requested_model']!r}, got {row.get('model')!r}"
            )
    expected_pairs = {
        (case_id, replicate)
        for case_id in expected_ids
        for replicate in ("1", "2")
    }
    if seen_pairs != expected_pairs:
        missing = sorted(expected_pairs - seen_pairs)
        foreign = sorted(seen_pairs - expected_pairs)
        raise OfflineIntegrityError(
            f"assessment pair coverage mismatch: missing={missing}, foreign={foreign}"
        )
    rows = prepare_rows(raw_rows, cases)
    return {"rows": rows, "cases": cases, "manifest": manifest}


def record_doi(row: dict[str, Any]) -> str:
    return str(row.get("doi", "") or "").strip().lower()


def all_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(str(error) for error in row.get("validation_errors", []) or [])
    errors.extend(str(error) for error in row.get("coherence_errors", []) or [])
    if row.get("technical_error"):
        errors.append(f"technical: {row['technical_error']}")
    return errors


def error_taxonomy(error: str) -> str:
    lowered = error.lower()
    if "requires evidence" in lowered:
        return "requires-evidence"
    if "quote found in " in lowered and "declared " in lowered:
        return "source-label mismatch"
    if "quote" in lowered or "evidence" in lowered:
        return "grounding"
    if "coherence" in lowered or "requires i" in lowered:
        return "coherence"
    if "technical:" in lowered:
        return "technical"
    if "schema" in lowered:
        return "schema"
    return "other validation"


def pair_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["_model"], str(row.get("case_id", "")))].append(row)
    summaries: list[dict[str, Any]] = []
    for (model, case_id), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda row: row["_replicate"])
        complete = len(ordered) == 2 and {row["_replicate"] for row in ordered} == {"1", "2"}
        valid = complete and all(row["_valid"] for row in ordered)
        observed = set(
            fail
            for row in ordered
            for fail in (row.get("hard_fails") or [])
        )
        reproduced = (
            set(ordered[0].get("hard_fails") or []).intersection(
                ordered[1].get("hard_fails") or []
            )
            if valid
            else set()
        )
        first = ordered[0] if ordered else {}
        case = first.get("_case", {})
        summaries.append(
            {
                "model": model,
                "case_id": case_id,
                "rows": ordered,
                "case": case,
                "doi": record_doi(first),
                "label": first.get("_label", ""),
                "variant": first.get("variant") or case.get("variant", ""),
                "complete": complete,
                "valid": valid,
                "observed_hard_fails": observed,
                "reproduced_hard_fails": reproduced,
            }
        )
    return summaries


def reproduced_hard_fails(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], set[str]]:
    """Return the intersection of hard-fails for complete valid pairs only."""

    return {
        (summary["model"], summary["case_id"]): set(summary["reproduced_hard_fails"])
        for summary in pair_summaries(rows)
    }


def validate_allowlist(allowlist: Iterable[str]) -> frozenset[str]:
    selected = frozenset(str(item) for item in allowlist)
    if selected not in ALLOWED_ALLOWLISTS:
        raise PolicyError(
            "terminal allowlist must be exactly empty or "
            f"{{{I1_CRITERION}}}; got {sorted(selected)}"
        )
    return selected


def is_title_only(summary: dict[str, Any]) -> bool:
    return str(summary.get("variant", "")).lower() in {"title_only", "title-only"} or bool(
        summary.get("case", {}).get("title_only", False)
    )


def simulate_assisted_policy(
    summaries: list[dict[str, Any]],
    allowlist: Iterable[str] = POLICY_ALLOWLIST,
) -> dict[str, Any]:
    selected = validate_allowlist(allowlist)
    proposals: list[dict[str, Any]] = []
    human_routes: list[dict[str, Any]] = []
    include_safety_violations: list[dict[str, Any]] = []

    for summary in summaries:
        label = summary["label"]
        reproduced = summary["reproduced_hard_fails"]
        observed_other = summary["observed_hard_fails"] - {I1_CRITERION}
        reason = ""
        if not summary["complete"]:
            reason = "incomplete replicate pair"
        elif not summary["valid"]:
            reason = "invalid or technical assessment in pair"
        elif label == "include" and I1_CRITERION in reproduced:
            violation = {
                "case_id": summary["case_id"],
                "doi": summary["doi"],
                "reproduced_hard_fails": sorted(reproduced),
            }
            include_safety_violations.append(violation)
            reason = "reproduced I1 on include"
        elif label != "exclude":
            reason = "label is not exclude"
        elif is_title_only(summary):
            reason = "title-only case"
        elif I1_CRITERION not in selected:
            reason = "allowlist is empty"
        elif I1_CRITERION not in reproduced:
            reason = "I1 is not reproduced"
        elif observed_other:
            reason = "another hard-fail was observed; human route required"
        else:
            proposals.append(
                {
                    "case_id": summary["case_id"],
                    "doi": summary["doi"],
                    "proposal": "exclude",
                    "final_decision": "needs_human_validation",
                    "reproduced_hard_fails": sorted(reproduced),
                }
            )
            continue
        human_routes.append(
            {
                "case_id": summary["case_id"],
                "doi": summary["doi"],
                "label": label,
                "reason": reason,
            }
        )

    exclude_pairs = [summary for summary in summaries if summary["label"] == "exclude"]
    valid_exclude_pairs = [summary for summary in exclude_pairs if summary["valid"]]
    potential_false_negatives = [
        item["case_id"]
        for item in human_routes
        if item["label"] == "exclude"
    ]
    total = len(summaries)
    return {
        "allowlist": sorted(selected),
        "proposals": proposals,
        "human_routes": human_routes,
        "include_safety_violations": include_safety_violations,
        "potential_false_negative_case_ids": potential_false_negatives,
        "proposal_count": len(proposals),
        "proposal_rate_all_cases": len(proposals) / total if total else 0.0,
        "valid_exclude_count": len(valid_exclude_pairs),
        "proposal_rate_valid_exclude": (
            len(proposals) / len(valid_exclude_pairs) if valid_exclude_pairs else 0.0
        ),
        "human_route_count": len(human_routes),
        "human_route_rate": len(human_routes) / total if total else 0.0,
    }


def apply_terminal_rules(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    reproduced_i1 = [
        summary
        for summary in summaries
        if summary["valid"] and I1_CRITERION in summary["reproduced_hard_fails"]
    ]
    include_hits = [summary for summary in reproduced_i1 if summary["label"] == "include"]
    exclude_hits = [summary for summary in reproduced_i1 if summary["label"] == "exclude"]
    unique_exclude_dois = {summary["doi"] for summary in exclude_hits if summary["doi"]}
    if include_hits:
        status = "disqualified"
        reason = "Rule 1: reproduced I1 occurs on a valid include pair."
    elif len(unique_exclude_dois) < 3:
        status = "not_qualified"
        reason = (
            "Rule 2: fewer than 3 unique exclude DOIs carry reproduced I1 "
            "in the terminal corpus."
        )
    else:
        status = "qualified"
        reason = "Rules 1 and 2 passed; Rule 3 human verification remains pending."

    by_doi: dict[str, dict[str, Any]] = {}
    for summary in sorted(
        exclude_hits,
        key=lambda item: (
            hashlib.sha256(
                f"{item['doi']}:{I1_CRITERION}".encode("utf-8")
            ).hexdigest(),
            item["case_id"],
        ),
    ):
        by_doi.setdefault(summary["doi"], summary)
    sample = list(by_doi.values())[:RULE3_MAX_SAMPLE] if status == "qualified" else []
    return {
        "criterion_id": I1_CRITERION,
        "status": status,
        "reason": reason,
        "reproduced_include_hits": [item["case_id"] for item in include_hits],
        "reproduced_exclude_occurrences": len(exclude_hits),
        "reproduced_exclude_unique_dois": len(unique_exclude_dois),
        "reproduced_exclude_case_ids": [item["case_id"] for item in exclude_hits],
        "rule_3_sample": sample,
        "final_decision": "pending_human_checklist",
    }


def criterion_row(row: dict[str, Any], criterion_id: str) -> dict[str, Any]:
    for item in row.get("full_assessment", []) or []:
        if isinstance(item, dict) and item.get("id") == criterion_id:
            return item
    return {}


def build_human_checklist(
    results_dir: Path, rule_result: dict[str, Any]
) -> str:
    sample = rule_result["rule_3_sample"]
    lines = [
        "# Terminal calibration — I1 human verification checklist",
        "",
        f"Results directory: `{results_dir}`",
        "",
        "A final allowlist decision is forbidden until every sampled item is",
        "marked CONFIRMED or REFUSED by a human reviewer.",
        "",
        f"Criterion: `{I1_CRITERION}`",
        f"Rule status before Rule 3: `{rule_result['status']}`",
        "",
    ]
    if not sample:
        lines.append("No Rule-3 sample is generated because I1 is not qualified.")
    else:
        for index, summary in enumerate(sample, start=1):
            lines.extend(
                [
                    f"## {index}. {summary['case_id']}",
                    "",
                    f"- DOI: `{summary['doi']}`",
                    f"- Title: {summary['case'].get('title', '')}",
                ]
            )
            for replicate_row in sorted(
                summary["rows"], key=lambda row: int(str(row.get("replicate", "0")))
            ):
                replicate = replicate_row.get("replicate", "?")
                assessment = criterion_row(replicate_row, I1_CRITERION)
                lines.extend(
                    [
                        "",
                        f"### Replicate {replicate}",
                        f"- Status: `{assessment.get('status', 'unknown')}`",
                    ]
                )
                for evidence in assessment.get("evidence", []) or []:
                    lines.append(
                        f"- Citation [{evidence.get('source', '')}] : « {evidence.get('quote', '')} »"
                    )
                lines.append(f"- Reason: {assessment.get('reason', '')}")
            lines.extend(
                [
                    "",
                    "- Human verdict for pair: [ ] CONFIRMED  [ ] REFUSED — note:",
                    "",
                ]
            )
    lines.extend(
        [
            "## Summary",
            "",
            "| Criterion | Sample size | Confirmed | Refused | Final allowlist |",
            "|---|---:|---:|---:|---|",
            f"| {I1_CRITERION} | {len(sample)} |  |  | PENDING HUMAN VALIDATION |",
            "",
        ]
    )
    return "\n".join(lines)


def _legacy_criterion_row(summary: dict[str, Any], criterion_id: str) -> dict[str, Any]:
    """Compatibility helper for callers that still hold a pair summary."""

    for row in summary["rows"]:
        for item in row.get("full_assessment", []) or []:
            if isinstance(item, dict) and item.get("id") == criterion_id:
                return item
    return {}


def stability_report(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    valid_pairs = [summary for summary in summaries if summary["valid"]]
    identical = sum(
        len(summary["rows"]) == 2
        and set(summary["rows"][0].get("hard_fails") or [])
        == set(summary["rows"][1].get("hard_fails") or [])
        for summary in valid_pairs
    )
    i1_identical = sum(
        (I1_CRITERION in (summary["rows"][0].get("hard_fails") or []))
        == (I1_CRITERION in (summary["rows"][1].get("hard_fails") or []))
        for summary in valid_pairs
    )
    return {
        "valid_comparable_pairs": len(valid_pairs),
        "identical_hard_fail_pairs": identical,
        "hard_fail_stability": identical / len(valid_pairs) if valid_pairs else 0.0,
        "i1_identical_pairs": i1_identical,
        "i1_stability": i1_identical / len(valid_pairs) if valid_pairs else 0.0,
        "incomplete_or_invalid_pairs": len(summaries) - len(valid_pairs),
    }


def invalid_table(rows: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["_replicate"]].append(row)
    lines = [
        "| Replicate | Records | Invalid | Technical | Rate |",
        "|---:|---:|---:|---:|---:|",
    ]
    for replicate, group in sorted(groups.items()):
        invalid = sum(not row["_valid"] for row in group)
        technical = sum("technical_error" in row for row in group)
        lines.append(
            f"| {replicate} | {len(group)} | {invalid} | {technical} | "
            f"{invalid / len(group):.1%} |"
        )
    invalid = sum(not row["_valid"] for row in rows)
    technical = sum("technical_error" in row for row in rows)
    lines.append(
        f"| ALL | {len(rows)} | {invalid} | {technical} | "
        f"{invalid / len(rows):.1%} |"
    )
    return "\n".join(lines)


def reproduced_hard_fail_table(summaries: list[dict[str, Any]]) -> str:
    criteria = sorted(
        {
            criterion
            for summary in summaries
            for criterion in summary["reproduced_hard_fails"]
        }
        | {I1_CRITERION}
    )
    counts: Counter[tuple[str, str]] = Counter()
    for summary in summaries:
        label = summary["label"] or "other"
        for criterion in summary["reproduced_hard_fails"]:
            counts[(criterion, label)] += 1
    lines = [
        "| Criterion | Include | Exclude | Other |",
        "|---|---:|---:|---:|",
    ]
    for criterion in criteria:
        lines.append(
            f"| {criterion} | {counts[(criterion, 'include')]} | "
            f"{counts[(criterion, 'exclude')]} | {counts[(criterion, 'other')]} |"
        )
    return "\n".join(lines)


def render_report(
    results_dir: Path,
    rows: list[dict[str, Any]],
    cases: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    summaries: list[dict[str, Any]],
    rules: dict[str, Any],
    simulation: dict[str, Any],
) -> str:
    del cases
    taxonomy: Counter[str] = Counter()
    for row in rows:
        for error in all_errors(row):
            taxonomy[error_taxonomy(error)] += 1
    stability = stability_report(summaries)
    response_models = manifest["response_models"]
    if response_models:
        response_model_line = (
            "- Returned model identifiers: "
            + ", ".join(f"`{item}`" for item in response_models)
            + "."
        )
    else:
        response_model_line = (
            "- Returned model identifiers: aucun identifiant de modèle retourné "
            "n’a été observé (manifest response_models=[])."
        )
    lines = [
        "# Terminal assisted calibration report",
        "",
        f"Results directory: `{results_dir}`",
        "",
        "This report is offline-only. It performs no API calls and makes no",
        "final allowlist decision before human verification.",
        "",
        "## Frozen coverage and model identity",
        "",
        f"- Cases: {manifest.get('case_count', len(summaries))}/40.",
        f"- Assessment lines: {len(rows)}/80.",
        f"- Pair summaries: {len(summaries)}; valid comparable pairs: {stability['valid_comparable_pairs']}.",
        f"- Requested model: `{manifest.get('requested_model', '')}`.",
        response_model_line,
        "- Requested and response model identifiers are not conflated.",
        f"- Prompt SHA-256: `{manifest.get('prompt_sha256', '')}`.",
        f"- Criteria SHA-256: `{manifest.get('criteria_sha256', '')}`.",
        f"- Corpus SHA-256: `{manifest.get('corpus_sha256', '')}`.",
        f"- Anchor commit: `{manifest.get('anchor_commit', '')}`.",
        "",
        "## Coverage and errors",
        "",
        invalid_table(rows),
        "",
        "| Error class | Count |",
        "|---|---:|",
    ]
    for category in TAXONOMY_ORDER:
        lines.append(f"| {category} | {taxonomy[category]} |")
    for category in sorted(set(taxonomy) - set(TAXONOMY_ORDER)):
        lines.append(f"| {category} | {taxonomy[category]} |")

    lines.extend(
        [
            "",
            "## Replicate stability",
            "",
            f"- Global hard-fail stability: {stability['identical_hard_fail_pairs']}/{stability['valid_comparable_pairs']} valid pairs ({stability['hard_fail_stability']:.1%}).",
            f"- I1-specific stability: {stability['i1_identical_pairs']}/{stability['valid_comparable_pairs']} valid pairs ({stability['i1_stability']:.1%}).",
            f"- Incomplete or invalid pairs: {stability['incomplete_or_invalid_pairs']}.",
            "",
            "## Reproduced hard-fails by human label",
            "",
            reproduced_hard_fail_table(summaries),
            "",
            "## Reproduced I1 support",
            "",
            f"- Include pairs carrying reproduced I1: {', '.join(rules['reproduced_include_hits']) or 'none'}.",
            f"- Exclude occurrences carrying reproduced I1: {rules['reproduced_exclude_occurrences']}.",
            f"- Exclude unique DOI support: {rules['reproduced_exclude_unique_dois']}.",
            f"- Exclude case IDs: {', '.join(rules['reproduced_exclude_case_ids']) or 'none'}.",
            "",
            "## Assisted I1-only policy simulation",
            "",
            f"- Allowlist under measurement: {{{I1_CRITERION}}}.",
            f"- Proposals: {simulation['proposal_count']}/{len(summaries)} cases ({simulation['proposal_rate_all_cases']:.1%}).",
            f"- Proposals among valid exclude pairs: {len(simulation['proposals'])}/{simulation['valid_exclude_count']} ({simulation['proposal_rate_valid_exclude']:.1%}).",
            f"- Routed to human: {simulation['human_route_count']}/{len(summaries)} ({simulation['human_route_rate']:.1%}).",
            f"- Reproduced I1 include safety violations: {len(simulation['include_safety_violations'])}.",
            f"- Potential false-negative routing cases: {len(simulation['potential_false_negative_case_ids'])}.",
            "- Every proposal remains `needs_human_validation`; `exclude_final` is forbidden.",
            "",
            "### Proposed I1 exclusions",
            "",
        ]
    )
    if simulation["proposals"]:
        lines.extend(
            f"- {item['case_id']} — {item['doi']} — needs_human_validation"
            for item in simulation["proposals"]
        )
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            "### Safety violations",
            "",
        ]
    )
    if simulation["include_safety_violations"]:
        lines.extend(
            f"- {item['case_id']} — {item['doi']} — {', '.join(item['reproduced_hard_fails'])}"
            for item in simulation["include_safety_violations"]
        )
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            "## Historical Rules 1–3, I1 and reproduced pairs only",
            "",
            f"- Rule 1/2 status: `{rules['status']}` — {rules['reason']}",
            f"- Rule 2 unique DOI support: {rules['reproduced_exclude_unique_dois']} (minimum 3).",
            f"- Rule 3 sample size: {len(rules['rule_3_sample'])}.",
            "- Final allowlist status: `pending_human_checklist`.",
            "- No E2, E4, I4, or other criterion can extend the allowlist.",
            "",
            "## Residual v3 limits",
            "",
            "- v3 remains falsified: (a) and (g) passed; (b)–(f) failed.",
            "- v3 produced 14/62 invalid assessments and one reproduced E4 violation.",
            "- `blocD_005` reproduced E1 and E4 on an include label but did not reproduce I1; it remains a human case under the terminal policy.",
            "- No I1 hard-fail was reproduced in the v3 corpus.",
            "",
            "## Human verification gate",
            "",
            "The accompanying checklist must be completed before any final",
            "allowlist decision. A refusal disqualifies I1; no checklist entry",
            "can authorize a criterion other than I1.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(results_dir: Path) -> dict[str, Any]:
    rows, cases, manifest = load_records(results_dir)
    summaries = pair_summaries(rows)
    rules = apply_terminal_rules(summaries)
    simulation = simulate_assisted_policy(summaries)
    checklist_path = results_dir / "phase2_sample_checklist.md"
    checklist_path.write_text(
        build_human_checklist(results_dir, rules), encoding="utf-8"
    )
    report_path = results_dir / "final_calibration_report.md"
    report_path.write_text(
        render_report(results_dir, rows, cases, manifest, summaries, rules, simulation),
        encoding="utf-8",
    )
    return {
        "report_path": report_path,
        "checklist_path": checklist_path,
        "rules": rules,
        "simulation": simulation,
        "summaries": summaries,
    }


if __name__ == "__main__":
    try:
        args = parse_args()
        result = analyze(args.results_dir)
        print(f"REPORT={result['report_path']}")
        print(f"CHECKLIST={result['checklist_path']}")
        print("ALLOWLIST_FINAL=NEEDS_HUMAN_VALIDATION")
        print("API_CALLS=0")
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
