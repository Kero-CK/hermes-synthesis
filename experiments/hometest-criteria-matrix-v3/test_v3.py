#!/usr/bin/env python3
"""Executable checks for the frozen criteria-matrix v3 contract."""

from __future__ import annotations

import csv
import difflib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path


sys.dont_write_bytecode = True
V3_DIR = Path(__file__).resolve().parent
REVIEW_DIR = Path(
    r"C:\Users\cedri\Documents\Work\Obsidian\Hermes\Projets\Hermes Synthesis\Reviews\hometest-prompteng"
)
sys.path.insert(0, str(V3_DIR))

import run_microtest_v3 as harness  # noqa: E402
from analyze_v3 import reproduced_hard_fails  # noqa: E402
from run_microtest_v3 import (  # noqa: E402
    BLOCK_B_IDS,
    BLOCK_C_IDS,
    CASE_SPECS,
    BlocDError,
    FrozenIntegrityError,
    V1_PROMPT_PATH,
    V2_PROMPT_PATH,
    V3_PROMPT_PATH,
    apply_v3_prompt_delta,
    build_cases,
    check_frozen_integrity,
    load_jsonl,
    replicate_slots,
    validate_model_assessment_v3,
)


def assert_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def test_prompt_has_exactly_two_changes() -> None:
    v2 = V2_PROMPT_PATH.read_text(encoding="utf-8")
    v3 = V3_PROMPT_PATH.read_text(encoding="utf-8")
    assert_equal(v3, apply_v3_prompt_delta(v2), "v3 prompt transform")
    opcodes = [
        opcode
        for opcode in difflib.SequenceMatcher(
            None, v2.splitlines(), v3.splitlines(), autojunk=False
        ).get_opcodes()
        if opcode[0] != "equal"
    ]
    assert_equal(len(opcodes), 2, "v2→v3 prompt change count")
    if v3.count('"criterion_assessment.v3-microtest"') != 1:
        raise AssertionError("v3 schema rename must occur exactly once")
    if "criterion_assessment.v2-microtest" in v3:
        raise AssertionError("v2 schema name remains in v3 prompt")
    if harness.SOURCE_LABEL_INSERTION not in v3:
        raise AssertionError("source-label rule is absent from v3 prompt")


def test_both_frozen_integrity_checks_and_tampered_fixtures() -> None:
    result = check_frozen_integrity()
    if not result["v1_reference_manifest"].get("criteria_sha256"):
        raise AssertionError("v1 reference criteria hash is absent")
    if not result["v2_reference_manifest"].get("prompt_sha256"):
        raise AssertionError("v2 reference prompt hash is absent")

    with tempfile.TemporaryDirectory(prefix=".test-v3-integrity-", dir=V3_DIR) as directory:
        root = Path(directory)
        tampered_criteria = json.loads(
            harness.V1_CRITERIA_PATH.read_text(encoding="utf-8")
        )
        tampered_criteria["criteria"][0]["id"] = "TAMPERED_V3_ID"
        criteria_path = root / "criteria.json"
        criteria_path.write_text(json.dumps(tampered_criteria), encoding="utf-8")
        try:
            check_frozen_integrity(criteria_path=criteria_path)
        except FrozenIntegrityError as exc:
            if "v1 frozen-integrity check failed" not in str(exc):
                raise AssertionError(f"unexpected v1 tamper error: {exc}") from exc
        else:
            raise AssertionError("tampered v1 criteria fixture was accepted")

        tampered_v2 = dict(result["v2_reference_manifest"])
        tampered_v2["prompt_sha256"] = "0" * 64
        v2_manifest_path = root / "v2_run_manifest.json"
        v2_manifest_path.write_text(json.dumps(tampered_v2), encoding="utf-8")
        try:
            check_frozen_integrity(v2_reference_manifest_path=v2_manifest_path)
        except FrozenIntegrityError as exc:
            if "v2 base frozen-integrity check failed" not in str(exc):
                raise AssertionError(f"unexpected v2 tamper error: {exc}") from exc
        else:
            raise AssertionError("tampered v2 manifest fixture was accepted")


def test_mislabeled_title_quote_gets_distinct_message() -> None:
    integrity = check_frozen_integrity()
    rows = []
    for index, criterion in enumerate(integrity["llm_criteria"]):
        row: dict[str, object] = {
            "id": criterion["id"],
            "status": "not_reported",
            "evidence": [],
            "reason": "No citable span was supplied.",
        }
        if index == 0:
            row.update(
                {
                    "status": "met",
                    "evidence": [{"source": "S1", "quote": "Title quote"}],
                    "reason": "The test quote is in the title.",
                }
            )
        rows.append(row)
    assessment = {"schema": harness.SCHEMA, "criteria": rows}
    case = {
        "title": "Title quote",
        "abstract": "Abstract source.",
        "sentences": [{"source": "S1", "text": "Abstract source."}],
    }
    errors = validate_model_assessment_v3(
        assessment, case, integrity["llm_criteria"]
    )
    expected = "criteria[0].evidence[0].quote found in T, declared S1"
    if expected not in errors:
        raise AssertionError(f"rewritten source error missing: {errors}")
    if any("quote not found in S1" in error for error in errors):
        raise AssertionError(f"old source error survived: {errors}")


def synthetic_assessment_row(
    case_id: str, replicate: int, hard_fails: list[str], *, label: str = "exclude"
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "model": "deepseek-reasoner",
        "bloc": "B",
        "replicate": replicate,
        "human_label": label,
        "hard_fails": hard_fails,
        "validation_errors": [],
        "coherence_errors": [],
        "_valid": True,
        "_label": label,
        "_bloc": "B",
        "_replicate": str(replicate),
    }


def test_reproduced_hard_fail_logic() -> None:
    rows = [
        synthetic_assessment_row("same", 1, ["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"]),
        synthetic_assessment_row("same", 2, ["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"]),
        synthetic_assessment_row("flips", 1, ["E4_APPLICATION_WITHOUT_PROMPT_DETAIL"]),
        synthetic_assessment_row("flips", 2, ["I4_PRACTITIONER"]),
    ]
    reproduced = reproduced_hard_fails(rows)
    assert_equal(
        reproduced[("deepseek-reasoner", "same")],
        {"E4_APPLICATION_WITHOUT_PROMPT_DETAIL"},
        "reproduced hard-fail intersection",
    )
    assert_equal(reproduced[("deepseek-reasoner", "flips")], set(), "non-reproduced hard-fail")


def test_frozen_block_loading_and_unique_case_flag() -> None:
    cases, blocks, warnings, d_info = build_cases(REVIEW_DIR, dry_run=True)
    assert_equal(blocks["A"]["count"], len(CASE_SPECS), "block A count")
    assert_equal(blocks["B"]["count"], len(BLOCK_B_IDS), "block B count")
    assert_equal(blocks["C"]["count"], len(BLOCK_C_IDS), "block C count")
    assert_equal(blocks["D"]["count"], 0, "unlabelled D dry-run count")
    assert_equal(len(cases), 26, "A-C unique case count")
    assert_equal(len(replicate_slots(cases)), 52, "A-C call count")
    a_tp = next(case for case in cases if case["case_id"] == "tp_cot_counterfactual")
    if not a_tp["bloc_b_regression"]:
        raise AssertionError("tp_cot_counterfactual is not flagged in A")
    if "tp_cot_counterfactual" in blocks["B"]["case_ids"]:
        raise AssertionError("tp_cot_counterfactual was duplicated in B")
    if not warnings or d_info["status"] == "included":
        raise AssertionError("dry-run did not warn about unlabelled v3 blocD.csv")

    frozen = {row["case_id"]: row for row in load_jsonl(harness.FROZEN_CALIBRATION_CASES_PATH)}
    for block, case_ids in (("B", BLOCK_B_IDS), ("C", BLOCK_C_IDS)):
        actual = {case["case_id"]: case for case in cases if case["bloc"] == block}
        for case_id in case_ids:
            expected = dict(frozen[case_id])
            expected["bloc"] = block
            assert_equal(actual[case_id], expected, f"verbatim frozen {block} {case_id}")


def write_temp_bloc_d(path: Path, labels: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
        writer.writeheader()
        for index, label in enumerate(labels):
            writer.writerow(
                {
                    "doi": f"10.9999/v3-test-{index}",
                    "title": f"V3 test {index}",
                    "abstract": "A test abstract.",
                    "label": label,
                }
            )


def test_blocd_refusal_and_31_case_replicates() -> None:
    with tempfile.TemporaryDirectory(prefix=".test-v3-blocd-", dir=V3_DIR) as directory:
        path = Path(directory) / "blocD.csv"
        write_temp_bloc_d(path, ["", "include", "exclude", "include", "exclude"])
        original = harness.BLOCD_PATH
        harness.BLOCD_PATH = path
        try:
            try:
                build_cases(REVIEW_DIR, dry_run=False)
            except BlocDError as exc:
                if "empty label" not in str(exc):
                    raise AssertionError(f"unexpected D refusal: {exc}") from exc
            else:
                raise AssertionError("real-run builder accepted an empty D label")

            write_temp_bloc_d(path, ["include", "exclude", "include", "exclude", "include"])
            cases, blocks, warnings, d_info = build_cases(REVIEW_DIR, dry_run=True)
        finally:
            harness.BLOCD_PATH = original
    assert_equal(blocks["D"]["count"], 5, "labelled D count")
    assert_equal(len(cases), 31, "full unique case count")
    assert_equal(len(replicate_slots(cases)), 62, "full call count")
    if warnings or d_info["status"] != "included":
        raise AssertionError("labelled D was not included")
    counts = Counter(case["case_id"] for case, _replicate in replicate_slots(cases))
    if set(counts.values()) != {2}:
        raise AssertionError("not exactly two assessment lines per case")


def test_label_helper_is_byte_identical() -> None:
    v2_helper = harness.V2_DIR / "label_blocD.py"
    v3_helper = harness.V3_DIR / "label_blocD.py"
    assert_equal(v3_helper.read_bytes(), v2_helper.read_bytes(), "label helper bytes")


def main() -> int:
    tests = [
        ("PROMPT_DIFF", test_prompt_has_exactly_two_changes),
        ("FROZEN_INTEGRITY", test_both_frozen_integrity_checks_and_tampered_fixtures),
        ("SOURCE_DIAGNOSTIC", test_mislabeled_title_quote_gets_distinct_message),
        ("REPRODUCED_HARD_FAILS", test_reproduced_hard_fail_logic),
        ("FROZEN_BLOCKS", test_frozen_block_loading_and_unique_case_flag),
        ("BLOCD_AND_REPLICATES", test_blocd_refusal_and_31_case_replicates),
        ("LABEL_HELPER", test_label_helper_is_byte_identical),
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
