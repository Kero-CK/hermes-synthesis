#!/usr/bin/env python3
"""Criteria-matrix v3 micro-test harness with two frozen-integrity anchors."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

V3_DIR = Path(__file__).resolve().parent
V2_DIR = V3_DIR.parent / "hometest-criteria-matrix-v2"
V1_DIR = V3_DIR.parent / "hometest-criteria-matrix-v1"
V1_CALIBRATION_DIR = V3_DIR.parent / "hometest-criteria-matrix-v1-calibration"
V1_PROMPT_PATH = V1_DIR / "prompt.txt"
V1_CRITERIA_PATH = V1_DIR / "criteria.json"
V2_PROMPT_PATH = V2_DIR / "prompt.txt"
V3_PROMPT_PATH = V3_DIR / "prompt.txt"
REFERENCE_RUN = "20260715T135629864224Z"
REFERENCE_MANIFEST_PATH = V1_DIR / "results" / REFERENCE_RUN / "run_manifest.json"
V2_REFERENCE_RUN = "20260716T121416997291Z"
V2_REFERENCE_MANIFEST_PATH = (
    V2_DIR / "results" / V2_REFERENCE_RUN / "run_manifest.json"
)
FROZEN_CALIBRATION_RUN = "20260715T161454171501Z"
FROZEN_CALIBRATION_CASES_PATH = (
    V1_CALIBRATION_DIR
    / "results"
    / FROZEN_CALIBRATION_RUN
    / "cases.jsonl"
)
V2_BLOCD_PATH = V2_DIR / "blocD.csv"
BLOCD_PATH = V3_DIR / "blocD.csv"
N_REPLICATES = 2
V3_SCHEMA = "criterion_assessment.v3-microtest"

BLOCK_B_IDS = [
    "gold_002",
    "gold_003",
    "gold_007",
    "gold_013",
    "gold_015",
    "gold_019",
    "gold_023",
    "gold_026",
    "gold_028",
    "gold_032",
    "gold_034",
    "gold_039",
]
BLOCK_C_IDS = [
    "gold_031",
    "gold_033",
    "gold_036",
    "gold_038",
    "gold_040",
]
E4_TARGET_IDS = ["gold_033", "gold_036", "gold_038", "gold_039", "gold_040"]
I4_TARGET_IDS = ["gold_031"]

BLOCK_DESCRIPTIONS = {
    "A": "v1 non-regression oracle cases; tp_cot_counterfactual is flagged for block-B regression",
    "B": "v2 regression cases reloaded from the frozen calibration corpus",
    "C": "E4/I4 parasite targets reloaded from the frozen calibration corpus",
    "D": "fresh held-out records labelled before the run",
}

SOURCE_LABEL_INSERTION = (
    '- A quote copied from the title must use source "T". "S1", "S2", ... refer\n'
    '  only to abstract sentences; never label a title quote with an "S" source.'
)
EVIDENCE_ITEM_BULLET = (
    '- Every evidence item must be {"source": "<T or S1, S2, ...>", '
    '"quote": "<exact contiguous substring of that one sentence>"}.'
)

SUCCESS_CRITERIA = [
    {
        "id": "a",
        "text": "Zéro erreur « requires evidence », les deux réplicats. Échec = v3 falsifié.",
    },
    {
        "id": "b",
        "text": "Zéro erreur d'étiquetage de source (le nouveau message §2.2), les deux réplicats — c'est le critère qui définit le v3. Échec = falsifié.",
    },
    {
        "id": "c",
        "text": "Taux global d'assessments invalides ≤ 10 %.",
    },
    {
        "id": "d",
        "text": "Non-régression bloc A : critères v1 (b), (c), (e) tiennent (mêmes oracles), par réplicat.",
    },
    {
        "id": "e",
        "text": "Hard-fails parasites, sémantique production : sur les cibles E4 (gold_033/036/038/039/040) et I4 (gold_031), aucun hard-fail REPRODUIT dans les deux réplicats. Échec = falsifié.",
    },
    {
        "id": "f",
        "text": "Zéro faux hard-fail reproduit sur tout cas labellisé include, blocs confondus. Échec = falsifié.",
    },
    {
        "id": "g",
        "text": "Stabilité (mesure) : % de paires de réplicats à hard-fails identiques, reporté par bloc ; pas de seuil falsifiant, la politique exige déjà la reproduction.",
    },
]


# Reuse the v2 corpus/D workflow and the v1 validator without copying either
# validation implementation. The v1 path is also inserted explicitly because
# the v3 harness calls the frozen v1 functions directly below.
sys.path.insert(0, str(V2_DIR))
import run_microtest_v2 as v2_harness  # noqa: E402

sys.path.insert(0, str(V1_DIR))
from run_microtest import (  # noqa: E402
    AUTO_EXCLUDABLE,
    CASE_SPECS,
    COHERENCE_RULES,
    DEFAULT_REVIEW_DIR,
    HOLDOUT_SELECTION_RULE,
    MATCHER_SPEC,
    SCHEMA,
    SENTENCE_SPLIT_REGEX,
    VALID_STATUSES,
    AssessmentValidationError,
    build_prompt,
    build_user_message,
    call_api,
    derive_hard_fails,
    derive_phase1_route,
    normalize_span,
    parse_content,
    run_validator_self_test as v1_run_validator_self_test,
    sentence_records,
    sha256_text,
    validate_model_assessment,
    write_json,
    write_jsonl,
)


class FrozenIntegrityError(RuntimeError):
    """A frozen v1/v2 input or the two-change v3 prompt contract was altered."""


class BlocDError(RuntimeError):
    """Bloc D is unavailable or not labelled for a real run."""


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def canonical_doi(doi: str) -> str:
    return str(doi or "").strip().lower()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise FrozenIntegrityError(
            f"v3 prompt delta anchor {label!r} occurred {count} times, expected once"
        )
    return text.replace(old, new, 1)


def apply_v3_prompt_delta(v2_text: str) -> str:
    """Apply exactly Charter §2.1 and the mechanical schema rename."""

    text = replace_once(
        v2_text,
        EVIDENCE_ITEM_BULLET + "\n",
        EVIDENCE_ITEM_BULLET + "\n" + SOURCE_LABEL_INSERTION + "\n",
        "source-label insertion",
    )
    return replace_once(
        text,
        '"criterion_assessment.v2-microtest"',
        '"criterion_assessment.v3-microtest"',
        "schema rename",
    )


def check_frozen_integrity(
    *,
    v1_prompt_path: Path = V1_PROMPT_PATH,
    criteria_path: Path = V1_CRITERIA_PATH,
    v2_prompt_path: Path = V2_PROMPT_PATH,
    v3_prompt_path: Path = V3_PROMPT_PATH,
    v1_reference_manifest_path: Path = REFERENCE_MANIFEST_PATH,
    v2_reference_manifest_path: Path = V2_REFERENCE_MANIFEST_PATH,
) -> dict[str, Any]:
    """Check v1 criteria, v1 prompt, v2 base prompt, and the v3 delta."""

    v1_prompt = v1_prompt_path.read_text(encoding="utf-8")
    criteria_document = json.loads(criteria_path.read_text(encoding="utf-8"))
    llm_criteria = [
        item for item in criteria_document["criteria"] if item["evaluator"] == "llm"
    ]
    metadata_criteria = [
        item
        for item in criteria_document["criteria"]
        if item["evaluator"] == "metadata"
    ]
    v1_system_prompt = build_prompt(v1_prompt, llm_criteria)
    v1_prompt_sha256 = sha256_text(v1_system_prompt)
    criteria_sha256 = sha256_text(
        json.dumps(criteria_document, ensure_ascii=False, sort_keys=True)
    )
    v1_reference = json.loads(v1_reference_manifest_path.read_text(encoding="utf-8"))
    v1_mismatches: list[str] = []
    if v1_reference.get("prompt_sha256") != v1_prompt_sha256:
        v1_mismatches.append(
            f"prompt expected {v1_reference.get('prompt_sha256')!r}, got {v1_prompt_sha256!r}"
        )
    if v1_reference.get("criteria_sha256") != criteria_sha256:
        v1_mismatches.append(
            f"criteria expected {v1_reference.get('criteria_sha256')!r}, got {criteria_sha256!r}"
        )
    if v1_mismatches:
        raise FrozenIntegrityError(
            "v1 frozen-integrity check failed: " + "; ".join(v1_mismatches)
        )

    v2_prompt = v2_prompt_path.read_text(encoding="utf-8")
    v2_system_prompt = build_prompt(v2_prompt, llm_criteria)
    v2_prompt_sha256 = sha256_text(v2_system_prompt)
    v2_reference = json.loads(v2_reference_manifest_path.read_text(encoding="utf-8"))
    v2_mismatches: list[str] = []
    if v2_reference.get("prompt_sha256") != v2_prompt_sha256:
        v2_mismatches.append(
            f"prompt expected {v2_reference.get('prompt_sha256')!r}, got {v2_prompt_sha256!r}"
        )
    if v2_reference.get("criteria_sha256") != criteria_sha256:
        v2_mismatches.append(
            f"criteria expected {v2_reference.get('criteria_sha256')!r}, got {criteria_sha256!r}"
        )
    if v2_mismatches:
        raise FrozenIntegrityError(
            "v2 base frozen-integrity check failed: " + "; ".join(v2_mismatches)
        )

    v3_prompt = v3_prompt_path.read_text(encoding="utf-8")
    expected_v3_prompt = apply_v3_prompt_delta(v2_prompt)
    if v3_prompt != expected_v3_prompt:
        raise FrozenIntegrityError(
            "v3 prompt diff integrity check failed: prompt differs from the two charter changes"
        )
    v3_system_prompt = build_prompt(v3_prompt, llm_criteria)
    return {
        "criteria_document": criteria_document,
        "llm_criteria": llm_criteria,
        "metadata_criteria": metadata_criteria,
        "v1_prompt": v1_prompt,
        "v2_prompt": v2_prompt,
        "v3_prompt": v3_prompt,
        "v1_system_prompt": v1_system_prompt,
        "v2_system_prompt": v2_system_prompt,
        "v3_system_prompt": v3_system_prompt,
        "v1_prompt_sha256": v1_prompt_sha256,
        "v2_prompt_sha256": v2_prompt_sha256,
        "v3_prompt_sha256": sha256_text(v3_system_prompt),
        "criteria_sha256": criteria_sha256,
        "v1_reference_manifest": v1_reference,
        "v2_reference_manifest": v2_reference,
    }


def load_frozen_block(block: str, case_ids: list[str]) -> list[dict[str, Any]]:
    source_rows = load_jsonl(FROZEN_CALIBRATION_CASES_PATH)
    indexed = {row["case_id"]: row for row in source_rows}
    missing = [case_id for case_id in case_ids if case_id not in indexed]
    if missing:
        raise RuntimeError(
            f"Frozen calibration cases missing for block {block}: {', '.join(missing)}"
        )
    cases: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = dict(indexed[case_id])
        case["bloc"] = block
        cases.append(case)
    return cases


def build_block_a(review_dir: Path) -> list[dict[str, Any]]:
    cases = v2_harness.build_block_a(review_dir)
    for case in cases:
        if case["case_id"] == "tp_cot_counterfactual":
            case["bloc_b_regression"] = True
    return cases


def load_v2_bloc_d_dois() -> set[str]:
    if not V2_BLOCD_PATH.is_file():
        raise FrozenIntegrityError(f"v2 blocD.csv is missing: {V2_BLOCD_PATH}")
    return {
        canonical_doi(row.get("doi", ""))
        for row in load_csv_rows(V2_BLOCD_PATH)
        if canonical_doi(row.get("doi", ""))
    }


def write_bloc_d(rows: list[dict[str, str]], output_path: Path = BLOCD_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
        writer.writeheader()
        writer.writerows(rows)


def generate_bloc_d(review_dir: Path, output_path: Path = BLOCD_PATH) -> dict[str, Any]:
    """Select five fresh candidates and leave their labels empty."""

    candidates_path = review_dir / "candidates.csv"
    gold_path = review_dir / "gold_set.csv"
    v2_dois = load_v2_bloc_d_dois()
    method = (
        "candidate rows with usable doi/title/abstract, DOI absent from gold_set.csv "
        "and v2 blocD.csv, unique canonical DOI, sorted by sha256(doi.lower()), first five"
    )
    if not candidates_path.is_file() or not gold_path.is_file():
        write_bloc_d([], output_path)
        return {"method": method, "excluded_v2_dois": sorted(v2_dois), "proposed_dois": []}
    rows = load_csv_rows(candidates_path)
    if not rows or not {"doi", "title", "abstract"}.issubset(rows[0].keys()):
        write_bloc_d([], output_path)
        return {"method": method, "excluded_v2_dois": sorted(v2_dois), "proposed_dois": []}
    gold_dois = {
        canonical_doi(row.get("doi", "")) for row in load_csv_rows(gold_path)
    }
    candidates: dict[str, dict[str, str]] = {}
    for row in rows:
        doi = canonical_doi(row.get("doi", ""))
        title = (row.get("title", "") or "").strip()
        abstract = (row.get("abstract", "") or "").strip()
        if not doi or doi in gold_dois or doi in v2_dois or not title or not abstract:
            continue
        candidates.setdefault(
            doi,
            {
                "doi": row.get("doi", "") or doi,
                "title": title,
                "abstract": abstract,
                "label": "",
            },
        )
    selected = sorted(
        candidates.values(),
        key=lambda row: hashlib.sha256(
            canonical_doi(row["doi"]).encode("utf-8")
        ).hexdigest(),
    )[:5]
    write_bloc_d(selected, output_path)
    return {
        "method": method,
        "excluded_v2_dois": sorted(v2_dois),
        "proposed_dois": [canonical_doi(row["doi"]) for row in selected],
    }


def read_bloc_d(path: Path = BLOCD_PATH) -> list[dict[str, str]]:
    try:
        return v2_harness.read_bloc_d(path)
    except v2_harness.BlocDError as exc:
        raise BlocDError(str(exc)) from exc


def build_block_d(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return v2_harness.build_block_d(rows)


def build_cases(
    review_dir: Path, *, dry_run: bool
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str], dict[str, Any]]:
    blocks: dict[str, list[dict[str, Any]]] = {
        "A": build_block_a(review_dir),
        "B": load_frozen_block("B", BLOCK_B_IDS),
        "C": load_frozen_block("C", BLOCK_C_IDS),
    }
    warnings: list[str] = []
    d_info: dict[str, Any] = {
        "path": str(BLOCD_PATH),
        "status": "not_included",
        "proposed_dois": [],
    }
    try:
        d_rows = read_bloc_d(BLOCD_PATH)
    except BlocDError as exc:
        if not dry_run:
            raise
        warnings.append(str(exc))
        d_info["status"] = f"not_included: {exc}"
    else:
        blocks["D"] = build_block_d(d_rows)
        d_info["status"] = "included"
        d_info["proposed_dois"] = [canonical_doi(row["doi"]) for row in d_rows]
    blocks.setdefault("D", [])
    cases = [case for block in ("A", "B", "C", "D") for case in blocks[block]]
    block_manifest = {
        block: {
            "description": BLOCK_DESCRIPTIONS[block],
            "case_ids": [case["case_id"] for case in blocks[block]],
            "count": len(blocks[block]),
        }
        for block in ("A", "B", "C", "D")
    }
    return cases, block_manifest, warnings, d_info


def case_sources(case: dict[str, Any]) -> dict[str, str]:
    sources = {"T": str(case.get("title", "") or "")}
    raw_sentences = case.get("sentences")
    if raw_sentences is None:
        raw_sentences = sentence_records(str(case.get("abstract", "") or ""))
    for index, item in enumerate(raw_sentences, start=1):
        if isinstance(item, dict):
            source = str(item.get("source") or f"S{index}")
            text = str(item.get("text") or "")
        else:
            source = f"S{index}"
            text = str(item)
        sources[source] = text
    return sources


QUOTE_NOT_FOUND_RE = re.compile(
    r"^(criteria\[(?P<criterion>\d+)\]\.evidence\[(?P<evidence>\d+)\])\.quote not found in (?P<declared>\S+)$"
)


def rewrite_quote_source_error(
    error: str, assessment: dict[str, Any], case: dict[str, Any]
) -> str:
    match = QUOTE_NOT_FOUND_RE.match(error)
    if not match:
        return error
    criteria_rows = assessment.get("criteria")
    if not isinstance(criteria_rows, list):
        return error
    criterion_index = int(match.group("criterion"))
    evidence_index = int(match.group("evidence"))
    if criterion_index >= len(criteria_rows):
        return error
    criterion_row = criteria_rows[criterion_index]
    evidence = criterion_row.get("evidence") if isinstance(criterion_row, dict) else None
    if not isinstance(evidence, list) or evidence_index >= len(evidence):
        return error
    evidence_item = evidence[evidence_index]
    quote = evidence_item.get("quote") if isinstance(evidence_item, dict) else None
    if not isinstance(quote, str) or not normalize_span(quote):
        return error
    declared = match.group("declared")
    normalized_quote = normalize_span(quote)
    for source, text in case_sources(case).items():
        if source == declared:
            continue
        if normalized_quote in normalize_span(text):
            return f"{match.group(1)}.quote found in {source}, declared {declared}"
    return error


def validate_model_assessment_v3(
    assessment: dict[str, Any],
    case: dict[str, Any],
    llm_criteria: list[dict[str, Any]],
) -> list[str]:
    """Call v1 validation unchanged, rewriting only its source diagnostic."""

    errors = validate_model_assessment(assessment, case, llm_criteria)
    return [rewrite_quote_source_error(error, assessment, case) for error in errors]


def assessment_base(case: dict[str, Any], model: str, replicate: int) -> dict[str, Any]:
    result = v2_harness.assessment_base(case, model, replicate)
    result["bloc_b_regression"] = bool(case.get("bloc_b_regression", False))
    return result


def process_model_assessment(
    model_assessment: dict[str, Any],
    content: str,
    case: dict[str, Any],
    model: str,
    replicate: int,
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
    criteria_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    validation_view = dict(model_assessment)
    if validation_view.get("schema") == V3_SCHEMA:
        validation_view["schema"] = SCHEMA
    validation_errors = validate_model_assessment_v3(
        validation_view, case, llm_criteria
    )
    full_assessment, coherence, complete = v2_harness.assemble_full_assessment(
        model_assessment, case, criteria, llm_criteria, metadata_criteria
    )
    hard_fails = derive_hard_fails(full_assessment, criteria_by_id) if complete else []
    route = (
        derive_phase1_route(full_assessment, criteria_by_id)
        if complete and not validation_errors and not coherence
        else "invalid_assessment"
    )
    result = assessment_base(case, model, replicate)
    result.update(
        {
            "validation_errors": validation_errors,
            "coherence_errors": coherence,
            "hard_fails": hard_fails,
            "phase1_route": route,
            "model_content": content,
            "full_assessment": full_assessment,
        }
    )
    return result


def invalid_result(
    case: dict[str, Any], model: str, replicate: int, error: str, content: str = ""
) -> dict[str, Any]:
    result = assessment_base(case, model, replicate)
    result.update(
        {
            "validation_errors": [error],
            "coherence_errors": [],
            "hard_fails": [],
            "phase1_route": "invalid_assessment",
            "model_content": content,
            "full_assessment": [],
        }
    )
    return result


def manifest(
    args: argparse.Namespace,
    run_id: str,
    models: list[str],
    integrity: dict[str, Any],
    cases: list[dict[str, Any]],
    blocks: dict[str, dict[str, Any]],
    warnings: list[str],
    bloc_d_info: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "temperature": 0.0,
        "models": models,
        "prompt_sha256": integrity["v3_prompt_sha256"],
        "v1_prompt_sha256": integrity["v1_prompt_sha256"],
        "v2_prompt_sha256": integrity["v2_prompt_sha256"],
        "criteria_sha256": integrity["criteria_sha256"],
        "assessment_schema": V3_SCHEMA,
        "v1_assessment_schema": SCHEMA,
        "phase1_auto_excludable": [],
        "review_dir": str(args.review_dir),
        "dry_run": bool(args.dry_run),
        "git_commit": None,
        "matcher_spec": list(MATCHER_SPEC),
        "sentence_segmentation_regex": SENTENCE_SPLIT_REGEX,
        "sentence_segmentation_abbreviation_guard": (
            r"do not split when the text immediately before the boundary ends with "
            r"\b(?:i\.e\.|e\.g\.|etc\.)$ (case-insensitive)"
        ),
        "coherence_rules": list(COHERENCE_RULES),
        "holdout_selection_rule": HOLDOUT_SELECTION_RULE,
        "oracle": [
            {
                "case_id": spec["case_id"],
                "category": spec["category"],
                "expected_primary": spec["expected_primary"],
                "accepted_alternatives": list(spec["accepted_alternatives"]),
            }
            for spec in CASE_SPECS
        ],
        "reference_run": REFERENCE_RUN,
        "v2_reference_run": V2_REFERENCE_RUN,
        "frozen_prompt_source": {
            "path": str(V1_PROMPT_PATH),
            "sha256": integrity["v1_prompt_sha256"],
        },
        "frozen_criteria_source": {
            "path": str(V1_CRITERIA_PATH),
            "sha256": integrity["criteria_sha256"],
        },
        "frozen_v2_prompt_source": {
            "path": str(V2_PROMPT_PATH),
            "sha256": integrity["v2_prompt_sha256"],
            "manifest": str(V2_REFERENCE_MANIFEST_PATH),
        },
        "frozen_calibration_cases_source": {
            "path": str(FROZEN_CALIBRATION_CASES_PATH),
            "sha256": sha256_file(FROZEN_CALIBRATION_CASES_PATH),
            "run_id": FROZEN_CALIBRATION_RUN,
        },
        "blocks": blocks,
        "n_replicates": N_REPLICATES,
        "call_count": len(cases) * N_REPLICATES,
        "success_criteria": SUCCESS_CRITERIA,
        "blocD": {**bloc_d_info, "path": str(BLOCD_PATH)},
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "messages_path": "user_messages.jsonl",
        "warnings": warnings,
        "notes": [
            "Block A is rebuilt from CASE_SPECS; tp_cot_counterfactual is flagged bloc_b_regression=true and is not duplicated in block B.",
            "Blocks B and C are copied from the frozen v1 calibration cases JSONL; the bloc field is the only added case field there.",
            "The v1 validator and derivation functions are imported unchanged; v3 rewrites only quote-source diagnostic messages.",
            "git_commit is null because this implementation performs no Git commands.",
            "A real run refuses to start until blocD.csv contains five non-empty labels.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--models", default="deepseek-reasoner")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--generate-bloc-d",
        action="store_true",
        help="Generate the deterministic five-record blocD.csv proposal and exit.",
    )
    return parser.parse_args()


def print_case_counts(blocks: dict[str, dict[str, Any]], total: int) -> None:
    for block in ("A", "B", "C", "D"):
        print(f"BLOCK_{block}_CASES={blocks[block]['count']}")
    print(f"CASES={total}")
    print(f"CALLS={total * N_REPLICATES}")
    print(f"N_REPLICATES={N_REPLICATES}")


def replicate_slots(cases: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    return [
        (case, replicate)
        for case in cases
        for replicate in range(1, N_REPLICATES + 1)
    ]


def main() -> int:
    args = parse_args()
    if args.generate_bloc_d:
        info = generate_bloc_d(args.review_dir)
        print(f"BLOCD_PATH={BLOCD_PATH}")
        print(f"BLOCD_METHOD={info['method']}")
        print(f"V2_BLOCD_EXCLUDED={','.join(info['excluded_v2_dois'])}")
        print(f"BLOCD_DOIS={','.join(info['proposed_dois'])}")
        print(f"BLOCD_ROWS={len(info['proposed_dois'])}")
        return 0

    integrity = check_frozen_integrity()
    criteria = integrity["criteria_document"]["criteria"]
    llm_criteria = integrity["llm_criteria"]
    metadata_criteria = integrity["metadata_criteria"]
    criteria_by_id = {criterion["id"]: criterion for criterion in criteria}
    if AUTO_EXCLUDABLE:
        raise RuntimeError("v3 requires AUTO_EXCLUDABLE to remain empty")
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    cases, blocks, warnings, bloc_d_info = build_cases(
        args.review_dir, dry_run=args.dry_run
    )
    if not args.dry_run:
        endpoint = os.environ.get("LLM_API_ENDPOINT", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        if not endpoint or not api_key:
            raise RuntimeError("LLM_API_ENDPOINT and LLM_API_KEY are required")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = "dryrun" if args.dry_run else "results"
    run_dir = V3_DIR / output_root / run_id
    write_jsonl(run_dir / "cases.jsonl", cases)
    write_jsonl(
        run_dir / "user_messages.jsonl",
        [
            {
                "case_id": case["case_id"],
                "bloc": case["bloc"],
                "message": build_user_message(case),
            }
            for case in cases
        ],
    )
    write_json(
        run_dir / "run_manifest.json",
        manifest(args, run_id, models, integrity, cases, blocks, warnings, bloc_d_info),
    )

    print("FROZEN_V1_INTEGRITY=PASS")
    print("FROZEN_V2_BASE_INTEGRITY=PASS")
    print("FROZEN_PROMPT_INTEGRITY=PASS")
    print(f"V1_PROMPT_SHA256={integrity['v1_prompt_sha256']}")
    print(f"V2_PROMPT_SHA256={integrity['v2_prompt_sha256']}")
    print(f"V3_PROMPT_SHA256={integrity['v3_prompt_sha256']}")
    print(f"CRITERIA_SHA256={integrity['criteria_sha256']}")
    for warning in warnings:
        print(f"WARNING={warning}")
    print_case_counts(blocks, len(cases))

    if args.dry_run:
        self_test = v1_run_validator_self_test(llm_criteria)
        self_test["v3_schema"] = V3_SCHEMA
        write_json(run_dir / "validator_self_test.json", self_test)
        print(f"DRY_RUN_DIR={run_dir}")
        print("VALIDATOR_SELF_TEST=PASS")
        return 0

    technical_failures: list[str] = []
    for model in models:
        model_rows: list[dict[str, Any]] = []
        for case in cases:
            for replicate in range(1, N_REPLICATES + 1):
                print(f"[{model}] {case['case_id']} r{replicate}", flush=True)
                raw_path = run_dir / "raw" / model / f"{case['case_id']}.r{replicate}.json"
                try:
                    raw_response = call_api(
                        endpoint,
                        api_key,
                        model,
                        integrity["v3_system_prompt"],
                        build_user_message(case),
                    )
                    write_json(raw_path, raw_response)
                    content, model_assessment = parse_content(raw_response)
                except AssessmentValidationError as exc:
                    model_rows.append(
                        invalid_result(case, model, replicate, str(exc), exc.content)
                    )
                    continue
                except Exception as exc:
                    technical_failures.append(
                        f"{model}/{case['case_id']}/r{replicate}: {exc}"
                    )
                    result = assessment_base(case, model, replicate)
                    result.update({"technical_error": str(exc)})
                    model_rows.append(result)
                    continue
                model_rows.append(
                    process_model_assessment(
                        model_assessment,
                        content,
                        case,
                        model,
                        replicate,
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
    except (FrozenIntegrityError, BlocDError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
