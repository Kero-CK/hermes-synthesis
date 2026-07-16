# Implementation plan — terminal assisted calibration

## Scope

This phase closes the criteria-matrix screening optimization track. It does
not create a v4 prompt, alter the frozen criteria, or change the matcher or
validator. All new files are confined to this directory.

## Files

- `[NEW]` `PREREGISTRATION-FINAL-CALIBRATION.md` — freezes the 40-record
  corpus, two-replicate design, assisted I1-only policy, and no-post-
  observation rules.
- `[NEW]` `run_final_calibration.py` — imports the frozen v3 harness and v1
  calibration helpers, checks the v1/v2/v3/corpus anchors, supports an
  API-free dry-run, and records requested versus observed model identifiers.
- `[NEW]` `analyze_final_calibration.py` — offline pair/reproduction analysis,
  I1-only assisted-policy simulation, Rules 1–3 measurement, and the blank
  human checklist.
- `[NEW]` `test_final_calibration.py` — integrity, corpus, reproduction,
  policy-safety, allowlist, and model-identity tests.
- `[NEW]` `DEVIATIONS-FINAL-CALIBRATION.md` — records interpretations and
  exact verification outputs.

## Verification sequence

1. Run the existing v1-calibration and v3 test suites with bytecode writes
   disabled.
2. Run `test_final_calibration.py` with bytecode writes disabled.
3. Run the final calibration dry-run; it must report 40 cases, 80 slots,
   and `API_CALLS=0`.
4. Run `git diff --check` and inspect the short status.
5. Commit only the six files in this directory with the preregistered
   anchoring message. Stop and request Cedric's explicit authorization before
   any real 80-call run.
