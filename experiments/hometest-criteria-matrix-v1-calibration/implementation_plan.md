# Calibration implementation plan

- `[NEW] run_calibration.py`: import the frozen v1 harness, verify prompt and
  criteria hashes, build all gold-set cases in CSV order, support dry-run and
  the later API-backed execution path, and persist calibration manifests and
  assessments.
- `[NEW] PREREGISTRATION-CALIBRATION.md`: record the fixed candidate criteria,
  disqualification, support, and sampling rules verbatim.
- `[NEW] analyze_calibration.py`: offline route, validity, hard-fail,
  stratification, allowlist, simulation, and phase-2 sampling analysis.
- `[NEW] test_calibration.py`: direct-executable tests for case construction,
  integrity checks, rules, and deterministic sampling.
- `[NEW] DEVIATIONS-CALIBRATION.md`: record interpretations and exact local
  verification outputs.

All new files and generated dry-run artifacts stay under this calibration
directory. The v1 harness, prompt, criteria, and reference results are read
only and imported or read from their existing locations.
