#!/usr/bin/env python3
"""Calibration harness built on the frozen criteria-matrix v1 harness."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Keep imports and all generated artifacts inside the calibration workflow from
# creating bytecode in the read-only v1 directory.
sys.dont_write_bytecode = True

CALIBRATION_DIR = Path(__file__).resolve().parent
V1_DIR = CALIBRATION_DIR.parent / "hometest-criteria-matrix-v1"
FROZEN_PROMPT_PATH = V1_DIR / "prompt.txt"
FROZEN_CRITERIA_PATH = V1_DIR / "criteria.json"
REFERENCE_RUN = "20260715T135629864224Z"
REFERENCE_MANIFEST_PATH = V1_DIR / "results" / REFERENCE_RUN / "run_manifest.json"

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
    normalize_span,
    parse_content,
    segment_sentences,
    sentence_records,
    sha256_text,
    validate_model_assessment,
    write_json,
    write_jsonl,
    run_validator_self_test as v1_run_validator_self_test,
)


CANDIDATE_CRITERIA = [
    "E1_NO_ACTIONABLE_TECHNIQUE",
    "E2_MODEL_TRAINING_ONLY",
    "E4_APPLICATION_WITHOUT_PROMPT_DETAIL",
    "E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE",
    "I1_PROMPT_TECHNIQUE",
    "I4_PRACTITIONER",
]

OBJECTIVE_TEXT = (
    "Objectif : fonder la allowlist `auto_excludable` du modèle "
    "deepseek-reasoner sous le prompt v1 gelé. Ce run ne teste pas le prompt "
    "(déjà validé) ; il mesure."
)
CANDIDATE_CRITERIA_TEXT = (
    "Critères candidats : E1_NO_ACTIONABLE_TECHNIQUE, E2_MODEL_TRAINING_ONLY, "
    "E4_APPLICATION_WITHOUT_PROMPT_DETAIL, "
    "E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE, I1_PROMPT_TECHNIQUE, "
    "I4_PRACTITIONER. I2_REPRODUCIBLE et E3_BENCHMARK_ONLY sont exclus "
    "d'office (phase 2 du micro-test : 0/2 et 1/2 confirmés). "
    "L'auto-exclusion depuis un titre seul reste interdite indépendamment de "
    "la allowlist."
)
RULE_1_TEXT = (
    "Règle 1 (disqualification mécanique) : un critère candidat X est "
    "disqualifié si X apparaît dans les hard_fails d'AU MOINS UN record "
    "labellisé include avec assessment valide (zéro validation_error, zéro "
    "coherence_error)."
)
RULE_2_TEXT = (
    "Règle 2 (support minimal) : X doit être un hard-fail sur au moins 3 DOI "
    "uniques labellisés exclude avec assessment valide, en cumulant micro-test "
    "v1 et calibration (un même DOI présent dans les deux corpus ou sous "
    "plusieurs variantes ne compte qu'une fois)."
)
RULE_3_TEXT = (
    "Règle 3 (vérification humaine échantillonnée) : pour chaque X encore "
    "qualifié, échantillon d'au plus 5 instances de hard-fail sur des records "
    "exclude avec assessment valide, hors les 7 DOI du micro-test (déjà "
    "vérifiés en phase 2) ; sélection déterministe par tri croissant de "
    "sha256(doi_minuscule + \":\" + criterion_id). Exigence : 100 % de "
    "CONFIRMÉ sur l'échantillon — un seul REFUSÉ retire X de la allowlist "
    "jusqu'au v2."
)
ALERT_RULE_TEXT = (
    "Signal d'alerte (reporté, non disqualifiant) : hard-fails de X sur des "
    "records include au sein d'assessments INVALIDES — comptés et listés dans "
    "le rapport."
)
NO_POST_OBSERVATION_TEXT = (
    "Aucune modification du prompt, des critères, du matcher ou de ces règles "
    "après observation des réponses."
)


class FrozenIntegrityError(RuntimeError):
    """The frozen v1 prompt or criteria no longer matches the reference run."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument(
        "--models",
        default="deepseek-reasoner",
        help="Comma-separated OpenAI-compatible model identifiers.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build artifacts and run the validator self-test without calling an API.",
    )
    return parser.parse_args()


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_csv_by_doi(path: Path) -> dict[str, dict[str, str]]:
    rows = load_csv_rows(path)
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        doi = (row.get("doi", "") or "").strip().lower()
        if doi:
            indexed[doi] = row
    return indexed


def canonical_doi(doi: str) -> str:
    return doi.strip().lower()


def microtest_dois() -> set[str]:
    return {canonical_doi(str(spec["doi"])) for spec in CASE_SPECS}


def check_frozen_integrity(
    prompt_path: Path = FROZEN_PROMPT_PATH,
    criteria_path: Path = FROZEN_CRITERIA_PATH,
    reference_manifest_path: Path = REFERENCE_MANIFEST_PATH,
) -> dict[str, Any]:
    """Verify the v1 source files against the recorded reference manifest."""

    prompt_template = prompt_path.read_text(encoding="utf-8")
    criteria_document = json.loads(criteria_path.read_text(encoding="utf-8"))
    llm_criteria = [
        item for item in criteria_document["criteria"] if item["evaluator"] == "llm"
    ]
    system_prompt = build_prompt(prompt_template, llm_criteria)
    prompt_hash = sha256_text(system_prompt)
    criteria_hash = sha256_text(
        json.dumps(criteria_document, ensure_ascii=False, sort_keys=True)
    )
    reference = json.loads(reference_manifest_path.read_text(encoding="utf-8"))
    mismatches: list[str] = []
    if reference.get("prompt_sha256") != prompt_hash:
        mismatches.append(
            f"prompt_sha256 expected {reference.get('prompt_sha256')!r}, got {prompt_hash!r}"
        )
    if reference.get("criteria_sha256") != criteria_hash:
        mismatches.append(
            f"criteria_sha256 expected {reference.get('criteria_sha256')!r}, got {criteria_hash!r}"
        )
    if mismatches:
        raise FrozenIntegrityError(
            "frozen prompt integrity check failed: " + "; ".join(mismatches)
        )
    return {
        "prompt_template": prompt_template,
        "criteria_document": criteria_document,
        "llm_criteria": llm_criteria,
        "system_prompt": system_prompt,
        "prompt_sha256": prompt_hash,
        "criteria_sha256": criteria_hash,
        "reference_manifest": reference,
    }


def build_calibration_cases(review_dir: Path) -> list[dict[str, Any]]:
    """Build every gold-set row in source order, without sampling or filtering."""

    gold_path = review_dir / "gold_set.csv"
    if not gold_path.is_file():
        raise RuntimeError(f"gold_set.csv is inaccessible: {gold_path}")
    gold_rows = load_csv_rows(gold_path)
    candidates_path = review_dir / "candidates.csv"
    candidates = load_csv_by_doi(candidates_path) if candidates_path.is_file() else {}
    known_microtest_dois = microtest_dois()

    cases: list[dict[str, Any]] = []
    for index, row in enumerate(gold_rows, start=1):
        doi = row.get("doi", "") or ""
        abstract = row.get("abstract", "") or ""
        metadata = candidates.get(canonical_doi(doi), {})
        cases.append(
            {
                "case_id": f"gold_{index:03d}",
                "doi": doi,
                "title": row.get("title", "") or "",
                "abstract": abstract,
                "human_label": row.get("label", "") or "",
                "abstract_source_original": row.get("abstract_source", "") or "",
                "stratum": row.get("stratum", "") or "",
                "publication_year": metadata.get("publication_year", "") or "",
                "language": metadata.get("language", "") or "",
                "sentences": sentence_records(abstract),
                "variant": "title_abstract",
                "in_microtest": canonical_doi(doi) in known_microtest_dois,
            }
        )
    return cases


def assemble_full_assessment(
    model_assessment: dict[str, Any],
    case: dict[str, Any],
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """Assemble rows using v1 evaluators; validation itself stays in v1."""

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
        isinstance(row.get("status"), str)
        and row["status"] in VALID_STATUSES
        for row in full_assessment
    )
    return (
        full_assessment,
        coherence_errors(full_assessment) if status_valid else [],
        complete,
    )


def assessment_base(case: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "doi": case["doi"],
        "model": model,
        "variant": case["variant"],
        "human_label": case["human_label"],
        "stratum": case["stratum"],
        "in_microtest": case["in_microtest"],
    }


def process_model_assessment(
    model_assessment: dict[str, Any],
    content: str,
    case: dict[str, Any],
    model: str,
    criteria: list[dict[str, Any]],
    llm_criteria: list[dict[str, Any]],
    metadata_criteria: list[dict[str, Any]],
    criteria_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    validation = validate_model_assessment(model_assessment, case, llm_criteria)
    full_assessment, coherence, complete = assemble_full_assessment(
        model_assessment,
        case,
        criteria,
        llm_criteria,
        metadata_criteria,
    )
    hard_fails = (
        derive_hard_fails(full_assessment, criteria_by_id) if complete else []
    )
    route = (
        derive_phase1_route(full_assessment, criteria_by_id)
        if complete and not validation and not coherence
        else "invalid_assessment"
    )
    result = assessment_base(case, model)
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


def current_git_commit() -> tuple[str, str | None]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=CALIBRATION_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return "", f"git_commit unavailable: {exc}"
    return completed.stdout.strip(), None


def calibration_manifest(
    run_id: str,
    args: argparse.Namespace,
    models: list[str],
    integrity: dict[str, Any],
    cases: list[dict[str, Any]],
    warnings: list[str],
    git_commit: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "temperature": 0.0,
        "models": models,
        "prompt_sha256": integrity["prompt_sha256"],
        "criteria_sha256": integrity["criteria_sha256"],
        "assessment_schema": SCHEMA,
        "phase1_auto_excludable": sorted(AUTO_EXCLUDABLE),
        "review_dir": str(args.review_dir),
        "dry_run": bool(args.dry_run),
        "git_commit": git_commit,
        "matcher_spec": list(MATCHER_SPEC),
        "sentence_segmentation_regex": SENTENCE_SPLIT_REGEX,
        "sentence_segmentation_abbreviation_guard": (
            r"do not split when the text immediately before the boundary ends with "
            r"\b(?:i\.e\.|e\.g\.|etc\.)$ (case-insensitive)"
        ),
        "coherence_rules": list(COHERENCE_RULES),
        "holdout_selection_rule": HOLDOUT_SELECTION_RULE,
        "oracle": [],
        "reference_run": REFERENCE_RUN,
        "frozen_prompt_source": {
            "path": str(FROZEN_PROMPT_PATH),
            "sha256": integrity["prompt_sha256"],
        },
        "frozen_criteria_source": {
            "path": str(FROZEN_CRITERIA_PATH),
            "sha256": integrity["criteria_sha256"],
        },
        "candidate_criteria": list(CANDIDATE_CRITERIA),
        "candidate_criteria_text": CANDIDATE_CRITERIA_TEXT,
        "disqualification_rules": [RULE_1_TEXT, RULE_2_TEXT],
        "sampling_rule": RULE_3_TEXT,
        "alert_rule": ALERT_RULE_TEXT,
        "no_post_observation_changes": NO_POST_OBSERVATION_TEXT,
        "case_count": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "messages_path": "user_messages.jsonl",
        "warnings": warnings,
        "notes": [
            "Calibration consumes every gold_set.csv row in CSV order.",
            "The v1 holdout_selection_rule is recorded for manifest compatibility but is not applied to calibration.",
            "The v1 prompt, criteria, matcher, and validation functions are read-only inputs.",
            "No calibration oracle or acceptance field is produced.",
            "AUTO_EXCLUDABLE remains empty during measurement.",
        ],
    }


def main() -> int:
    args = parse_args()
    integrity = check_frozen_integrity()
    criteria = integrity["criteria_document"]["criteria"]
    llm_criteria = integrity["llm_criteria"]
    metadata_criteria = [
        item for item in criteria if item["evaluator"] == "metadata"
    ]
    criteria_by_id = {item["id"]: item for item in criteria}
    if len(criteria_by_id) != len(criteria):
        raise RuntimeError("Duplicate criterion ID in frozen criteria")
    if AUTO_EXCLUDABLE:
        raise RuntimeError("Calibration requires AUTO_EXCLUDABLE to remain empty")
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    warnings: list[str] = []

    if args.dry_run:
        try:
            cases = build_calibration_cases(args.review_dir)
        except Exception as exc:
            cases = []
            warnings.append(f"review data unavailable in dry-run: {exc}")
    else:
        endpoint = os.environ.get("LLM_API_ENDPOINT", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        if not endpoint or not api_key:
            raise RuntimeError("LLM_API_ENDPOINT and LLM_API_KEY are required")
        cases = build_calibration_cases(args.review_dir)

    git_commit, git_warning = current_git_commit()
    if git_warning:
        warnings.append(git_warning)
        if args.dry_run:
            print(f"WARNING: {git_warning}", file=sys.stderr)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = "dryrun" if args.dry_run else "results"
    run_dir = CALIBRATION_DIR / output_root / run_id
    write_jsonl(run_dir / "cases.jsonl", cases)
    write_jsonl(
        run_dir / "user_messages.jsonl",
        [
            {"case_id": case["case_id"], "message": build_user_message(case)}
            for case in cases
        ],
    )
    write_json(
        run_dir / "run_manifest.json",
        calibration_manifest(
            run_id, args, models, integrity, cases, warnings, git_commit
        ),
    )

    print("FROZEN_PROMPT_INTEGRITY=PASS")
    print(f"PROMPT_SHA256={integrity['prompt_sha256']}")
    print(f"CRITERIA_SHA256={integrity['criteria_sha256']}")

    if args.dry_run:
        self_test = v1_run_validator_self_test(llm_criteria)
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
                    endpoint,
                    api_key,
                    model,
                    integrity["system_prompt"],
                    user_message,
                )
                write_json(raw_path, raw_response)
                content, model_assessment = parse_content(raw_response)
            except AssessmentValidationError as exc:
                result = assessment_base(case, model)
                result.update(
                    {
                        "validation_errors": [str(exc)],
                        "coherence_errors": [],
                        "hard_fails": [],
                        "phase1_route": "invalid_assessment",
                        "model_content": exc.content,
                        "full_assessment": [],
                    }
                )
                model_rows.append(result)
                continue
            except Exception as exc:
                technical_failures.append(f"{model}/{case['case_id']}: {exc}")
                result = assessment_base(case, model)
                result["technical_error"] = str(exc)
                model_rows.append(result)
                continue

            model_rows.append(
                process_model_assessment(
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
    except FrozenIntegrityError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
