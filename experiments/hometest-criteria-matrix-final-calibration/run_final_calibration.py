#!/usr/bin/env python3
"""Terminal assisted calibration on the frozen 40-record v3 corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

FINAL_DIR = Path(__file__).resolve().parent
V3_DIR = FINAL_DIR.parent / "hometest-criteria-matrix-v3"
V1_CALIBRATION_DIR = FINAL_DIR.parent / "hometest-criteria-matrix-v1-calibration"
FROZEN_CASES_PATH = (
    V1_CALIBRATION_DIR
    / "results"
    / "20260715T161454171501Z"
    / "cases.jsonl"
)
V3_PROMPT_PATH = V3_DIR / "prompt.txt"
V1_CRITERIA_PATH = V3_DIR.parent / "hometest-criteria-matrix-v1" / "criteria.json"

EXPECTED_CORPUS_SHA256 = (
    "70dff2678d974883126b480c4b2884ed2b1da059598b3f7f235972e58935b7cf"
)
EXPECTED_V3_PROMPT_SHA256 = (
    "b723fbb068da8eefec9d77cfa162d2090ee680676ace3b9b5c1b2614d8c0c047"
)
EXPECTED_CRITERIA_SHA256 = (
    "41ddfe013dd6e662c01b7297de76088924e3bbab0b5dd1248dffdb50b8f7ca21"
)
REQUESTED_MODEL = "deepseek-reasoner"
N_REPLICATES = 2
POLICY_ALLOWLIST = frozenset({"I1_PROMPT_TECHNIQUE"})
TERMINAL_CALIBRATION = True
PROMPT_OPTIMIZATION_CLOSED = True

sys.path.insert(0, str(V3_DIR))
import run_microtest_v3 as v3_harness  # noqa: E402


class FinalIntegrityError(RuntimeError):
    """A frozen terminal-calibration input does not match its anchor."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_frozen_cases(path: Path = FROZEN_CASES_PATH) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    if digest != EXPECTED_CORPUS_SHA256:
        raise FinalIntegrityError(
            f"corpus SHA-256 mismatch: expected {EXPECTED_CORPUS_SHA256}, got {digest}"
        )
    cases = load_jsonl(path)
    if len(cases) != 40:
        raise FinalIntegrityError(f"expected 40 frozen cases, got {len(cases)}")
    case_ids = [str(case.get("case_id", "")) for case in cases]
    if len(set(case_ids)) != 40 or any(not case_id for case_id in case_ids):
        raise FinalIntegrityError("frozen corpus case IDs are not exactly 40 unique non-empty IDs")
    if any(str(case.get("human_label", "")).strip() not in {"include", "exclude"} for case in cases):
        raise FinalIntegrityError("frozen corpus contains an empty or invalid human label")
    return raw, cases


def check_final_integrity(
    *,
    v3_prompt_path: Path = V3_PROMPT_PATH,
    criteria_path: Path = V1_CRITERIA_PATH,
    corpus_path: Path = FROZEN_CASES_PATH,
) -> dict[str, Any]:
    """Run historical v1/v2/v3 checks and the terminal corpus anchor."""

    integrity = v3_harness.check_frozen_integrity(
        v3_prompt_path=v3_prompt_path,
        criteria_path=criteria_path,
    )
    if integrity["v3_prompt_sha256"] != EXPECTED_V3_PROMPT_SHA256:
        raise FinalIntegrityError(
            "v3 prompt SHA-256 mismatch: "
            f"expected {EXPECTED_V3_PROMPT_SHA256}, got {integrity['v3_prompt_sha256']}"
        )
    if integrity["criteria_sha256"] != EXPECTED_CRITERIA_SHA256:
        raise FinalIntegrityError(
            "criteria SHA-256 mismatch: "
            f"expected {EXPECTED_CRITERIA_SHA256}, got {integrity['criteria_sha256']}"
        )
    corpus_bytes, cases = load_frozen_cases(corpus_path)
    return {
        **integrity,
        "corpus_bytes": corpus_bytes,
        "cases": cases,
        "corpus_sha256": sha256_bytes(corpus_bytes),
    }


def current_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=FINAL_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def replicate_slots(cases: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    return [
        (case, replicate)
        for case in cases
        for replicate in range(1, N_REPLICATES + 1)
    ]


def assessment_base(
    case: dict[str, Any], model: str, replicate: int
) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "doi": case.get("doi", ""),
        "model": model,
        "bloc": "gold_set",
        "replicate": replicate,
        "variant": case.get("variant", "title_abstract"),
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
    """Use the imported v3 diagnostic and v1-derived assembly functions."""

    validation_view = dict(model_assessment)
    if validation_view.get("schema") == v3_harness.V3_SCHEMA:
        validation_view["schema"] = v3_harness.SCHEMA
    validation_errors = v3_harness.validate_model_assessment_v3(
        validation_view, case, llm_criteria
    )
    full_assessment, coherence_errors, complete = (
        v3_harness.v2_harness.assemble_full_assessment(
            model_assessment,
            case,
            criteria,
            llm_criteria,
            metadata_criteria,
        )
    )
    hard_fails = (
        v3_harness.derive_hard_fails(full_assessment, criteria_by_id)
        if complete
        else []
    )
    route = (
        v3_harness.derive_phase1_route(full_assessment, criteria_by_id)
        if complete and not validation_errors and not coherence_errors
        else "invalid_assessment"
    )
    result = assessment_base(case, model, replicate)
    result.update(
        {
            "validation_errors": validation_errors,
            "coherence_errors": coherence_errors,
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


def build_manifest(
    args: argparse.Namespace,
    run_id: str,
    model: str,
    integrity: dict[str, Any],
    cases: list[dict[str, Any]],
    anchor_commit: str,
    response_models: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "temperature": 0.0,
        "requested_model": model,
        "models": [model],
        "response_models": sorted(response_models or []),
        "prompt_sha256": integrity["v3_prompt_sha256"],
        "criteria_sha256": integrity["criteria_sha256"],
        "corpus_sha256": integrity["corpus_sha256"],
        "assessment_schema": v3_harness.V3_SCHEMA,
        "anchor_commit": anchor_commit,
        "git_commit": anchor_commit,
        "terminal_calibration": TERMINAL_CALIBRATION,
        "prompt_optimization_closed": PROMPT_OPTIMIZATION_CLOSED,
        "policy": {
            "allowlist": sorted(POLICY_ALLOWLIST),
            "reproduction_required": True,
            "human_validation_required": True,
            "proposal_route": "needs_human_validation",
            "final_exclusion_route": "forbidden",
            "title_only_proposal": False,
            "other_hard_fail_route": "human",
        },
        "corpus_source": str(FROZEN_CASES_PATH),
        "case_count": len(cases),
        "expected_case_count": 40,
        "n_replicates": N_REPLICATES,
        "call_count": len(cases) * N_REPLICATES,
        "expected_call_slots": 80,
        "case_ids": [case["case_id"] for case in cases],
        "messages_path": "user_messages.jsonl",
        "dry_run": bool(args.dry_run),
        "api_calls_made": 0,
        "completed_assessment_lines": 0,
        "technical_failure_count": 0,
        "frozen_sources": {
            "v3_prompt": {"path": str(V3_PROMPT_PATH), "sha256": integrity["v3_prompt_sha256"]},
            "v1_criteria": {"path": str(V1_CRITERIA_PATH), "sha256": integrity["criteria_sha256"]},
            "corpus": {"path": str(FROZEN_CASES_PATH), "sha256": integrity["corpus_sha256"]},
        },
        "notes": [
            "The prompt, criteria, matcher, and validator are imported frozen inputs.",
            "Only I1_PROMPT_TECHNIQUE can create an assisted proposal.",
            "Every proposal remains needs_human_validation; exclude_final is forbidden.",
            "Requested and response model identifiers are deliberately separate.",
            "No final allowlist decision is made before the human checklist.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        default=REQUESTED_MODEL,
        help="Exactly one requested OpenAI-compatible model identifier.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def print_integrity(integrity: dict[str, Any], anchor_commit: str) -> None:
    print("FROZEN_V1_INTEGRITY=PASS")
    print("FROZEN_V2_BASE_INTEGRITY=PASS")
    print("FROZEN_PROMPT_INTEGRITY=PASS")
    print("FROZEN_CORPUS_INTEGRITY=PASS")
    print(f"V3_PROMPT_SHA256={integrity['v3_prompt_sha256']}")
    print(f"CRITERIA_SHA256={integrity['criteria_sha256']}")
    print(f"CORPUS_SHA256={integrity['corpus_sha256']}")
    print(f"ANCHOR_COMMIT={anchor_commit}")
    print(f"CASES={len(integrity['cases'])}")
    print(f"CALLS={len(integrity['cases']) * N_REPLICATES}")
    print(f"N_REPLICATES={N_REPLICATES}")


def main() -> int:
    args = parse_args()
    integrity = check_final_integrity()
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if models != [REQUESTED_MODEL]:
        raise RuntimeError(
            "terminal calibration is frozen to the requested model "
            f"{REQUESTED_MODEL!r}"
        )
    model = models[0]

    if not args.dry_run:
        endpoint = os.environ.get("LLM_API_ENDPOINT", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        if not endpoint or not api_key:
            raise RuntimeError("LLM_API_ENDPOINT and LLM_API_KEY are required")

    cases = integrity["cases"]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_root = FINAL_DIR / ("dryrun" if args.dry_run else "results")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cases.jsonl").write_bytes(integrity["corpus_bytes"])
    write_jsonl(
        run_dir / "user_messages.jsonl",
        [
            {"case_id": case["case_id"], "message": v3_harness.build_user_message(case)}
            for case in cases
        ],
    )
    anchor_commit = current_git_commit()
    manifest_path = run_dir / "run_manifest.json"
    write_json(
        manifest_path,
        build_manifest(args, run_id, model, integrity, cases, anchor_commit),
    )
    print_integrity(integrity, anchor_commit)

    if args.dry_run:
        self_test = v3_harness.v1_run_validator_self_test(integrity["llm_criteria"])
        write_json(run_dir / "validator_self_test.json", self_test)
        print(f"DRY_RUN_DIR={run_dir}")
        print("VALIDATOR_SELF_TEST=PASS")
        print("API_CALLS=0")
        return 0

    endpoint = os.environ["LLM_API_ENDPOINT"]
    api_key = os.environ["LLM_API_KEY"]
    criteria = integrity["criteria_document"]["criteria"]
    llm_criteria = integrity["llm_criteria"]
    metadata_criteria = integrity["metadata_criteria"]
    criteria_by_id = {criterion["id"]: criterion for criterion in criteria}
    technical_failures: list[str] = []
    response_models: set[str] = set()
    model_rows: list[dict[str, Any]] = []

    for case, replicate in replicate_slots(cases):
        print(f"[{model}] {case['case_id']} r{replicate}", flush=True)
        raw_path = run_dir / "raw" / model / f"{case['case_id']}.r{replicate}.json"
        try:
            raw_response = v3_harness.call_api(
                endpoint,
                api_key,
                model,
                integrity["v3_system_prompt"],
                v3_harness.build_user_message(case),
            )
            write_json(raw_path, raw_response)
            if isinstance(raw_response, dict) and raw_response.get("model"):
                response_models.add(str(raw_response["model"]))
            content, model_assessment = v3_harness.parse_content(raw_response)
        except v3_harness.AssessmentValidationError as exc:
            model_rows.append(
                invalid_result(case, model, replicate, str(exc), exc.content)
            )
            continue
        except Exception as exc:
            technical_failures.append(f"{model}/{case['case_id']}/r{replicate}: {exc}")
            result = assessment_base(case, model, replicate)
            result["technical_error"] = str(exc)
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
    final_manifest = build_manifest(
        args,
        run_id,
        model,
        integrity,
        cases,
        anchor_commit,
        sorted(response_models),
    )
    final_manifest.update(
        {
            "api_calls_made": len(model_rows),
            "completed_assessment_lines": len(model_rows),
            "technical_failure_count": len(technical_failures),
        }
    )
    write_json(manifest_path, final_manifest)
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
    except FinalIntegrityError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
