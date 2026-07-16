#!/usr/bin/env python3
"""Executable checks for the frozen criteria-matrix v2 micro-test contract."""

from __future__ import annotations

import csv
import difflib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path


sys.dont_write_bytecode = True
V2_DIR = Path(__file__).resolve().parent
REVIEW_DIR = Path(
    r"C:\Users\cedri\Documents\Work\Obsidian\Hermes\Projets\Hermes Synthesis\Reviews\hometest-prompteng"
)
sys.path.insert(0, str(V2_DIR))

import run_microtest_v2 as harness  # noqa: E402
from analyze_v2 import evaluate_v2  # noqa: E402
from run_microtest_v2 import (  # noqa: E402
    BLOCK_B_IDS,
    BLOCK_C_IDS,
    BLOCD_PATH,
    CASE_SPECS,
    BlocDError,
    FrozenIntegrityError,
    V1_PROMPT_PATH,
    V2_PROMPT_PATH,
    apply_v2_prompt_delta,
    build_cases,
    check_frozen_integrity,
    load_jsonl,
    replicate_slots,
)


def assert_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_prompt_has_exactly_four_changes() -> None:
    v1 = V1_PROMPT_PATH.read_text(encoding="utf-8")
    v2 = V2_PROMPT_PATH.read_text(encoding="utf-8")
    expected = apply_v2_prompt_delta(v1)
    assert_equal(v2, expected, "v2 prompt must be the four-change transform of v1")
    opcodes = [
        opcode
        for opcode in difflib.SequenceMatcher(
            None, v1.splitlines(), v2.splitlines(), autojunk=False
        ).get_opcodes()
        if opcode[0] != "equal"
    ]
    assert_equal(len(opcodes), 4, "prompt diff change count")
    if v2.count('"criterion_assessment.v2-microtest"') != 1:
        raise AssertionError("v2 schema rename must occur exactly once")
    if "criterion_assessment.v1-microtest" in v2:
        raise AssertionError("v1 schema name remains in the v2 prompt")


def test_frozen_integrity_pass_and_tampered_fixture_fail() -> None:
    result = check_frozen_integrity()
    if not result["reference_manifest"].get("prompt_sha256"):
        raise AssertionError("reference manifest prompt hash is absent")
    criteria = json.loads(harness.V1_CRITERIA_PATH.read_text(encoding="utf-8"))
    criteria["criteria"][0]["id"] = "TAMPERED_CRITERION_ID"
    with tempfile.TemporaryDirectory(prefix=".test-integrity-", dir=V2_DIR) as directory:
        tampered_path = Path(directory) / "criteria.json"
        tampered_path.write_text(json.dumps(criteria), encoding="utf-8")
        try:
            check_frozen_integrity(criteria_path=tampered_path)
        except FrozenIntegrityError as exc:
            if "frozen criteria integrity check failed" not in str(exc):
                raise AssertionError(f"unexpected tamper failure: {exc}") from exc
        else:
            raise AssertionError("tampered frozen manifest was accepted")


def test_frozen_block_loading_is_verbatim() -> None:
    cases, blocks, warnings, d_info = build_cases(REVIEW_DIR, dry_run=True)
    assert_equal(blocks["A"]["count"], len(CASE_SPECS), "block A count")
    assert_equal(blocks["B"]["count"], len(BLOCK_B_IDS), "block B count")
    assert_equal(blocks["C"]["count"], len(BLOCK_C_IDS), "block C count")
    assert_equal(blocks["D"]["count"], 0, "unlabelled block D dry-run count")
    assert_equal(len(cases), 28, "dry-run base case count")
    if not warnings or d_info["status"] == "included":
        raise AssertionError("dry-run did not warn about the unlabelled blocD.csv")

    frozen = {row["case_id"]: row for row in load_jsonl(harness.FROZEN_CALIBRATION_CASES_PATH)}
    for block, case_ids in (("B", BLOCK_B_IDS), ("C", BLOCK_C_IDS)):
        actual = {case["case_id"]: case for case in cases if case["bloc"] == block}
        for case_id in case_ids:
            expected = dict(frozen[case_id])
            expected["bloc"] = block
            assert_equal(actual[case_id], expected, f"frozen {block} case {case_id}")


def test_real_run_refuses_incomplete_bloc_d() -> None:
    with tempfile.TemporaryDirectory(prefix=".test-blocd-", dir=V2_DIR) as directory:
        incomplete = Path(directory) / "blocD.csv"
        with incomplete.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
            writer.writeheader()
            for index in range(5):
                writer.writerow(
                    {
                        "doi": f"10.9999/test-{index}",
                        "title": f"Test {index}",
                        "abstract": "An abstract.",
                        "label": "" if index == 0 else "exclude",
                    }
                )
        original = harness.BLOCD_PATH
        harness.BLOCD_PATH = incomplete
        try:
            try:
                build_cases(REVIEW_DIR, dry_run=False)
            except BlocDError as exc:
                if "empty label" not in str(exc):
                    raise AssertionError(f"unexpected bloc D refusal: {exc}") from exc
            else:
                raise AssertionError("real-run case builder accepted incomplete blocD.csv")
        finally:
            harness.BLOCD_PATH = original


def test_labelled_bloc_d_adds_five_cases() -> None:
    with tempfile.TemporaryDirectory(prefix=".test-blocd-", dir=V2_DIR) as directory:
        labelled = Path(directory) / "blocD.csv"
        with labelled.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
            writer.writeheader()
            for index in range(5):
                writer.writerow(
                    {
                        "doi": f"10.9999/labelled-{index}",
                        "title": f"Labelled {index}",
                        "abstract": "An abstract.",
                        "label": "exclude" if index % 2 else "include",
                    }
                )
        original = harness.BLOCD_PATH
        harness.BLOCD_PATH = labelled
        try:
            cases, blocks, warnings, d_info = build_cases(REVIEW_DIR, dry_run=True)
        finally:
            harness.BLOCD_PATH = original
        assert_equal(blocks["D"]["count"], 5, "labelled block D count")
        assert_equal(len(cases), 33, "labelled total case count")
        if warnings or d_info["status"] != "included":
            raise AssertionError("labelled block D was not included in dry-run")


def test_two_replicate_slots_per_case() -> None:
    cases, blocks, _warnings, _d_info = build_cases(REVIEW_DIR, dry_run=True)
    slots = replicate_slots(cases)
    assert_equal(len(slots), 2 * len(cases), "replicate slot count")
    counts = Counter(case["case_id"] for case, _replicate in slots)
    if set(counts.values()) != {2}:
        raise AssertionError(f"not exactly two assessment lines per case: {counts}")
    if {replicate for _case, replicate in slots} != {1, 2}:
        raise AssertionError("replicates are not numbered 1 and 2")
    if blocks["A"]["count"] + blocks["B"]["count"] + blocks["C"]["count"] != 28:
        raise AssertionError("unexpected dry-run block total")


def synthetic_row(
    case_id: str,
    replicate: int,
    *,
    hard_fails: list[str] | None = None,
    validation_errors: list[str] | None = None,
    label: str = "exclude",
    bloc: str = "B",
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "doi": f"10.9999/{case_id}",
        "model": "deepseek-reasoner",
        "bloc": bloc,
        "replicate": replicate,
        "human_label": label,
        "hard_fails": hard_fails or [],
        "phase1_route": "exclude" if hard_fails else "include",
        "validation_errors": validation_errors or [],
        "coherence_errors": [],
        "_case": {"case_id": case_id, "bloc": bloc, "human_label": label},
        "_valid": not validation_errors,
        "_label": label,
        "_bloc": bloc,
        "_replicate": str(replicate),
    }


def test_synthetic_criteria_a_and_f() -> None:
    stable = [
        synthetic_row("synthetic_001", replicate, hard_fails=["I1_PROMPT_TECHNIQUE"])
        for replicate in (1, 2)
    ] + [synthetic_row("synthetic_002", replicate) for replicate in (1, 2)]
    evaluation = evaluate_v2(stable)
    assert_equal(evaluation["criteria"]["a"]["status"], "PASS", "criterion (a) synthetic pass")
    assert_equal(evaluation["criteria"]["f"]["status"], "PASS", "criterion (f) synthetic pass")

    requires_evidence = list(stable)
    requires_evidence[0] = synthetic_row(
        "synthetic_001",
        1,
        hard_fails=["I1_PROMPT_TECHNIQUE"],
        validation_errors=["criterion I1 requires evidence"],
    )
    failed_a = evaluate_v2(requires_evidence)
    assert_equal(failed_a["criteria"]["a"]["status"], "FAIL", "criterion (a) synthetic failure")

    unstable = list(stable)
    unstable[1] = synthetic_row("synthetic_001", 2, hard_fails=["E1_NO_ACTIONABLE_TECHNIQUE"])
    failed_f = evaluate_v2(unstable)
    assert_equal(failed_f["criteria"]["f"]["status"], "FAIL", "criterion (f) synthetic failure")


def main() -> int:
    tests = [
        ("PROMPT_DIFF", test_prompt_has_exactly_four_changes),
        ("FROZEN_INTEGRITY", test_frozen_integrity_pass_and_tampered_fixture_fail),
        ("FROZEN_BLOCKS", test_frozen_block_loading_is_verbatim),
        ("BLOCD_REFUSAL", test_real_run_refuses_incomplete_bloc_d),
        ("BLOCD_COUNTS", test_labelled_bloc_d_adds_five_cases),
        ("REPLICATES", test_two_replicate_slots_per_case),
        ("CRITERIA_A_F", test_synthetic_criteria_a_and_f),
    ]
    for name, test in tests:
        test()
        print(f"{name}=PASS")
    print(f"TESTS={len(tests)}")
    print("ALL_TESTS=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TEST_FAILURE={exc}", file=sys.stderr)
        raise SystemExit(1)
