#!/usr/bin/env python3
"""Criteria-matrix v2 micro-test harness built on the frozen v1 harness."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

V2_DIR = Path(__file__).resolve().parent
V1_DIR = V2_DIR.parent / "hometest-criteria-matrix-v1"
V1_CALIBRATION_DIR = V2_DIR.parent / "hometest-criteria-matrix-v1-calibration"
V1_PROMPT_PATH = V1_DIR / "prompt.txt"
V1_CRITERIA_PATH = V1_DIR / "criteria.json"
V2_PROMPT_PATH = V2_DIR / "prompt.txt"
REFERENCE_RUN = "20260715T135629864224Z"
REFERENCE_MANIFEST_PATH = V1_DIR / "results" / REFERENCE_RUN / "run_manifest.json"
FROZEN_CALIBRATION_RUN = "20260715T161454171501Z"
FROZEN_CALIBRATION_CASES_PATH = (
    V1_CALIBRATION_DIR
    / "results"
    / FROZEN_CALIBRATION_RUN
    / "cases.jsonl"
)
BLOCD_PATH = V2_DIR / "blocD.csv"
N_REPLICATES = 2
V2_SCHEMA = "criterion_assessment.v2-microtest"

BLOCK_B_IDS = [
    "gold_002",
    "gold_003",
    "gold_007",
    "gold_013",
    "gold_014",
    "gold_015",
    "gold_016",
    "gold_019",
    "gold_023",
    "gold_026",
    "gold_028",
    "gold_032",
    "gold_034",
]
BLOCK_C_IDS = [
    "gold_031",
    "gold_033",
    "gold_036",
    "gold_038",
    "gold_039",
    "gold_040",
]

BLOCK_DESCRIPTIONS = {
    "A": "v1 non-regression oracle cases",
    "B": "calibration records exposing the v1 evidence disease",
    "C": "Rule-3 E4/I4 refusal cases",
    "D": "fresh held-out records labelled before the run",
}

DOMAIN_APPLICATION_INSERTION = (
    '- "A domain application" means the article\'s primary contribution is\n'
    "  applying an LLM to one specific task or domain. Surveys, overviews of\n"
    "  multiple applications, evaluation frameworks, and system or security\n"
    "  frameworks are not domain applications."
)
OLD_TIE_BREAKERS = (
    '- If you cannot produce a citable span, the status is "not_reported". '
    '"unclear" requires at least one citable span.\n'
    '- "not_met" requires a span whose content contradicts the criterion. A span '
    'merely related to the topic does not justify "not_met".'
)
NEW_TIE_BREAKERS = (
    OLD_TIE_BREAKERS
    + '\n- When an exclusion criterion simply does not apply to the article, there are only two valid answers: "not_met" WITH a span that contradicts the criterion, or "not_reported" with an empty evidence array. "not_met" with an empty evidence array is always invalid.'
)
OUTPUT_CONTRACT_CHECK = (
    'Before returning, check every criterion: if its status is "met", "not_met",\n'
    'or "unclear" and its evidence array is empty, change its status to\n'
    '"not_reported".'
)

SUCCESS_CRITERIA = [
    {
        "id": "a",
        "text": "Zéro erreur « requires evidence » sur l'ensemble du corpus, les deux réplicats. C'est le critère qui définit le v2 : s'il échoue, v2 falsifié.",
    },
    {
        "id": "b",
        "text": "Taux d'assessments invalides ≤ 10 % (v1 calibration : 32,5 %).",
    },
    {
        "id": "c",
        "text": "Bloc A : les critères (b), (c), (e) du PREREGISTRATION v1 tiennent encore (mêmes oracles). Toute régression = v2 falsifié.",
    },
    {
        "id": "d",
        "text": "Bloc C : E4 ∉ hard_fails sur les 5 cas refusés, dans les deux réplicats ; I4 ∉ hard_fails sur gold_031.",
    },
    {
        "id": "e",
        "text": "Zéro faux hard-fail sur tout cas labellisé include (assessment valide), blocs confondus.",
    },
    {
        "id": "f",
        "text": "Stabilité (mesure, seuil indicatif) : ensembles de hard-fails identiques entre réplicats sur ≥ 90 % des cas. Sous le seuil, v2 n'est pas falsifié mais l'exigence de reproduction avant auto-exclusion devient définitivement obligatoire dans la politique.",
    },
]


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
    coherence_errors,
    derive_hard_fails,
    derive_phase1_route,
    metadata_assessments,
    parse_content,
    run_validator_self_test as v1_run_validator_self_test,
    sentence_records,
    sha256_text,
    validate_model_assessment,
    write_json,
    write_jsonl,
)


class FrozenIntegrityError(RuntimeError):
    """A frozen v1 input or the four-change v2 prompt contract was altered."""


class BlocDError(RuntimeError):
    """Bloc D is unavailable or not labelled for a real run."""


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_csv_by_doi(path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in load_csv_rows(path):
        doi = canonical_doi(row.get("doi", ""))
        if doi:
            indexed[doi] = row
    return indexed


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
            f"v2 prompt delta anchor {label!r} occurred {count} times, expected once"
        )
    return text.replace(old, new, 1)


def apply_v2_prompt_delta(v1_text: str) -> str:
    """Apply exactly Charter §§2.1–2.3 and the mechanical schema rename."""

    decision_d_line = (
        "- [DECISION-D] Named practitioner prompting families (zero-shot prompting, "
        "few-shot / in-context examples, chain-of-thought prompting) count as "
        "identifiable, transferable prompting methods when the title or abstract "
        "states they were applied or compared."
    )
    text = replace_once(
        v1_text,
        decision_d_line + "\n\nSTATUS DEFINITIONS",
        decision_d_line
        + "\n"
        + DOMAIN_APPLICATION_INSERTION
        + "\n\nSTATUS DEFINITIONS",
        "2.1",
    )
    text = replace_once(text, OLD_TIE_BREAKERS, NEW_TIE_BREAKERS, "2.2")
    text = replace_once(
        text,
        "\nReturn every supplied criterion exactly once",
        "\n"
        + OUTPUT_CONTRACT_CHECK
        + "\n\nReturn every supplied criterion exactly once",
        "2.3",
    )
    text = replace_once(
        text,
        '"criterion_assessment.v1-microtest"',
        '"criterion_assessment.v2-microtest"',
        "schema rename",
    )
    return text


def check_frozen_integrity(
    *,
    v1_prompt_path: Path = V1_PROMPT_PATH,
    criteria_path: Path = V1_CRITERIA_PATH,
    v2_prompt_path: Path = V2_PROMPT_PATH,
    reference_manifest_path: Path = REFERENCE_MANIFEST_PATH,
) -> dict[str, Any]:
    v1_prompt = v1_prompt_path.read_text(encoding="utf-8")
    criteria_document = json.loads(criteria_path.read_text(encoding="utf-8"))
    llm_criteria = [
        item for item in criteria_document["criteria"] if item["evaluator"] == "llm"
    ]
    v1_system_prompt = build_prompt(v1_prompt, llm_criteria)
    v1_prompt_sha256 = sha256_text(v1_system_prompt)
    criteria_sha256 = sha256_text(
        json.dumps(criteria_document, ensure_ascii=False, sort_keys=True)
    )
    reference = json.loads(reference_manifest_path.read_text(encoding="utf-8"))
    mismatches: list[str] = []
    if reference.get("prompt_sha256") != v1_prompt_sha256:
        mismatches.append(
            f"v1 prompt hash expected {reference.get('prompt_sha256')!r}, got {v1_prompt_sha256!r}"
        )
    if reference.get("criteria_sha256") != criteria_sha256:
        mismatches.append(
            f"criteria hash expected {reference.get('criteria_sha256')!r}, got {criteria_sha256!r}"
        )
    if mismatches:
        raise FrozenIntegrityError(
            "frozen criteria integrity check failed: " + "; ".join(mismatches)
        )
    v2_prompt = v2_prompt_path.read_text(encoding="utf-8")
    expected_v2_prompt = apply_v2_prompt_delta(v1_prompt)
    if v2_prompt != expected_v2_prompt:
        raise FrozenIntegrityError(
            "v2 prompt diff integrity check failed: prompt differs from the four charter changes"
        )
    v2_system_prompt = build_prompt(v2_prompt, llm_criteria)
    return {
        "criteria_document": criteria_document,
        "llm_criteria": llm_criteria,
        "metadata_criteria": [
            item
            for item in criteria_document["criteria"]
            if item["evaluator"] == "metadata"
        ],
        "v1_prompt": v1_prompt,
        "v2_prompt": v2_prompt,
        "v1_system_prompt": v1_system_prompt,
        "v2_system_prompt": v2_system_prompt,
        "v1_prompt_sha256": v1_prompt_sha256,
        "v2_prompt_sha256": sha256_text(v2_system_prompt),
        "criteria_sha256": criteria_sha256,
        "reference_manifest": reference,
    }


def microtest_dois() -> set[str]:
    return {canonical_doi(spec["doi"]) for spec in CASE_SPECS}


def build_block_a(review_dir: Path) -> list[dict[str, Any]]:
    gold_path = review_dir / "gold_set.csv"
    if not gold_path.is_file():
        raise RuntimeError(f"gold_set.csv is inaccessible: {gold_path}")
    gold = load_csv_by_doi(gold_path)
    candidates_path = review_dir / "candidates.csv"
    candidates = load_csv_by_doi(candidates_path) if candidates_path.is_file() else {}
    cases: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        key = canonical_doi(spec["doi"])
        if key not in gold:
            raise RuntimeError(f"Gold-set DOI missing for block A: {spec['doi']}")
        row = gold[key]
        metadata = candidates.get(key, {})
        abstract = row.get("abstract", "") or ""
        if spec.get("variant") == "title_only_projection":
            abstract = ""
        case = dict(spec)
        case.update(
            {
                "bloc": "A",
                "title": row.get("title", "") or "",
                "abstract": abstract,
                "human_label": row.get("label", "") or "",
                "abstract_source_original": row.get("abstract_source", "") or "",
                "stratum": row.get("stratum", "") or "",
                "publication_year": metadata.get("publication_year", "") or "",
                "language": metadata.get("language", "") or "",
                "sentences": sentence_records(abstract),
                "in_microtest": True,
            }
        )
        cases.append(case)
    return cases


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


def write_bloc_d(rows: list[dict[str, str]], output_path: Path = BLOCD_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
        writer.writeheader()
        writer.writerows(rows)


def generate_bloc_d(review_dir: Path, output_path: Path = BLOCD_PATH) -> dict[str, Any]:
    """Propose five fresh records and leave every label empty."""

    candidates_path = review_dir / "candidates.csv"
    gold_path = review_dir / "gold_set.csv"
    method = (
        "candidate rows with usable doi/title/abstract, DOI not in gold_set.csv, "
        "unique canonical DOI, sorted by sha256(doi.lower()), first five"
    )
    if not candidates_path.is_file() or not gold_path.is_file():
        write_bloc_d([], output_path)
        return {"method": method, "proposed_dois": [], "usable": False}
    candidate_rows = load_csv_rows(candidates_path)
    if not candidate_rows or not {"doi", "title", "abstract"}.issubset(
        candidate_rows[0].keys()
    ):
        write_bloc_d([], output_path)
        return {"method": method, "proposed_dois": [], "usable": False}
    gold_dois = set(load_csv_by_doi(gold_path))
    candidates: dict[str, dict[str, str]] = {}
    for row in candidate_rows:
        doi = canonical_doi(row.get("doi", ""))
        title = (row.get("title", "") or "").strip()
        abstract = (row.get("abstract", "") or "").strip()
        if not doi or doi in gold_dois or not title or not abstract:
            continue
        candidates.setdefault(
            doi,
            {"doi": row.get("doi", "") or doi, "title": title, "abstract": abstract, "label": ""},
        )
    selected = sorted(
        candidates.values(),
        key=lambda row: hashlib.sha256(canonical_doi(row["doi"]).encode("utf-8")).hexdigest(),
    )[:5]
    write_bloc_d(selected, output_path)
    return {
        "method": method,
        "proposed_dois": [canonical_doi(row["doi"]) for row in selected],
        "usable": len(selected) == 5,
    }


def read_bloc_d(path: Path = BLOCD_PATH) -> list[dict[str, str]]:
    if not path.is_file():
        raise BlocDError(f"blocD.csv is missing: {path}")
    rows = load_csv_rows(path)
    required = {"doi", "title", "abstract", "label"}
    if not rows or not required.issubset(set(rows[0].keys()) if rows else set()):
        raise BlocDError("blocD.csv must contain five rows and columns doi,title,abstract,label")
    if len(rows) != 5:
        raise BlocDError(f"blocD.csv must contain exactly 5 records; found {len(rows)}")
    if any(not (row.get("label", "") or "").strip() for row in rows):
        raise BlocDError("blocD.csv has an empty label; Cedric must label all five records before a real run")
    return rows


def build_block_d(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        abstract = row.get("abstract", "") or ""
        cases.append(
            {
                "case_id": f"blocD_{index:03d}",
                "bloc": "D",
                "doi": row.get("doi", "") or "",
                "title": row.get("title", "") or "",
                "abstract": abstract,
                "human_label": row.get("label", "") or "",
                "abstract_source_original": "blocD",
                "stratum": "D",
                "publication_year": "",
                "language": "",
                "sentences": sentence_records(abstract),
                "variant": "title_abstract",
                "in_microtest": False,
            }
        )
    return cases


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


def assemble_full_assessment(
    model_assessment: dict[str, Any],
    case: dict[str, Any],
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], bool]:
    rows = model_assessment.get("criteria", [])
    rows_by_id = {
        row["id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    ordered_model_rows = [
        rows_by_id[criterion["id"]]
        for criterion in llm_criteria
        if criterion["id"] in rows_by_id
    ]
    deterministic_rows = metadata_assessments(case, metadata_criteria)
    full_by_id = {row["id"]: row for row in ordered_model_rows + deterministic_rows}
    full_assessment = [
        full_by_id[criterion["id"]]
        for criterion in criteria
        if criterion["id"] in full_by_id
    ]
    complete = len(full_assessment) == len(criteria)
    status_valid = complete and all(
        isinstance(row.get("status"), str) and row["status"] in VALID_STATUSES
        for row in full_assessment
    )
    return full_assessment, coherence_errors(full_assessment) if status_valid else [], complete


def assessment_base(case: dict[str, Any], model: str, replicate: int) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "doi": case["doi"],
        "model": model,
        "bloc": case["bloc"],
        "replicate": replicate,
        "variant": case["variant"],
        "human_label": case.get("human_label", ""),
        "stratum": case.get("stratum", ""),
        "in_microtest": bool(case.get("in_microtest", False)),
    }


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
    if validation_view.get("schema") == V2_SCHEMA:
        validation_view["schema"] = SCHEMA
    validation = validate_model_assessment(validation_view, case, llm_criteria)
    full_assessment, coherence, complete = assemble_full_assessment(
        model_assessment, case, criteria, llm_criteria, metadata_criteria
    )
    hard_fails = derive_hard_fails(full_assessment, criteria_by_id) if complete else []
    route = (
        derive_phase1_route(full_assessment, criteria_by_id)
        if complete and not validation and not coherence
        else "invalid_assessment"
    )
    result = assessment_base(case, model, replicate)
    result.update(
        {
            "validation_errors": validation,
            "coherence_errors": coherence,
            "hard_fails": hard_fails,
            "phase1_route": route,
            "model_content": content,
            "full_assessment": full_assessment,
        }
    )
    return result


def invalid_result(case: dict[str, Any], model: str, replicate: int, error: str, content: str = "") -> dict[str, Any]:
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
        "prompt_sha256": integrity["v2_prompt_sha256"],
        "v1_prompt_sha256": integrity["v1_prompt_sha256"],
        "criteria_sha256": integrity["criteria_sha256"],
        "assessment_schema": V2_SCHEMA,
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
        "frozen_prompt_source": {
            "path": str(V1_PROMPT_PATH),
            "sha256": integrity["v1_prompt_sha256"],
        },
        "frozen_criteria_source": {
            "path": str(V1_CRITERIA_PATH),
            "sha256": integrity["criteria_sha256"],
        },
        "frozen_calibration_cases_source": {
            "path": str(FROZEN_CALIBRATION_CASES_PATH),
            "sha256": sha256_file(FROZEN_CALIBRATION_CASES_PATH),
            "run_id": FROZEN_CALIBRATION_RUN,
        },
        "blocks": blocks,
        "n_replicates": N_REPLICATES,
        "success_criteria": SUCCESS_CRITERIA,
        "blocD": {
            **bloc_d_info,
            "path": str(BLOCD_PATH),
        },
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "messages_path": "user_messages.jsonl",
        "warnings": warnings,
        "notes": [
            "Block A is rebuilt from CASE_SPECS and the review directory; blocks B and C are copied from the frozen v1 calibration cases JSONL.",
            "Hard-fails are produced by the imported v1 validator/derivation functions; no acceptance field or oracle acceptance is produced.",
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
        print(f"BLOCD_DOIS={','.join(info['proposed_dois'])}")
        print(f"BLOCD_ROWS={len(info['proposed_dois'])}")
        return 0

    integrity = check_frozen_integrity()
    criteria = integrity["criteria_document"]["criteria"]
    llm_criteria = integrity["llm_criteria"]
    metadata_criteria = integrity["metadata_criteria"]
    criteria_by_id = {criterion["id"]: criterion for criterion in criteria}
    if AUTO_EXCLUDABLE:
        raise RuntimeError("v2 requires AUTO_EXCLUDABLE to remain empty")
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
    run_dir = V2_DIR / output_root / run_id
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

    print("FROZEN_PROMPT_INTEGRITY=PASS")
    print(f"V1_PROMPT_SHA256={integrity['v1_prompt_sha256']}")
    print(f"V2_PROMPT_SHA256={integrity['v2_prompt_sha256']}")
    print(f"CRITERIA_SHA256={integrity['criteria_sha256']}")
    for warning in warnings:
        print(f"WARNING={warning}")
    print_case_counts(blocks, len(cases))

    if args.dry_run:
        self_test = v1_run_validator_self_test(llm_criteria)
        self_test["v2_schema"] = V2_SCHEMA
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
                        integrity["v2_system_prompt"],
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
