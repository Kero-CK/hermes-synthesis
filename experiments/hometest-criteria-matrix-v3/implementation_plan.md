# Implementation plan — criteria-matrix v3 micro-test

- [MODIFY] `CHARTER.md`: append the dated schema and unique-case amendment.
- [NEW] `prompt.txt`: derive byte-for-byte from v2 with only the source-label
  evidence-contract insertion and the v3 schema rename.
- [NEW] `run_microtest_v3.py`: import the v1 validator and v2 harness patterns,
  perform both frozen-integrity checks, build blocks A–D, and run two
  replicates with an API-free dry-run.
- [NEW] `analyze_v3.py`: evaluate criteria (a)–(g), reproduced hard-fails,
  source-label diagnostics, and per-block stability offline.
- [NEW] `PREREGISTRATION-V3.md`: freeze the corrected 31-case corpus, D
  selection, replicates, criteria, and no-post-observation rule.
- [NEW] `test_v3.py`: verify the two-change prompt transform, both integrity
  anchors, the diagnostic rewrite, frozen corpus, D refusal, replicates, and
  reproduced-hard-fail logic.
- [NEW] `label_blocD.py`: byte-identical copy of the v2 labeling helper.
- [NEW] `blocD.csv`: deterministic five-record proposal with empty labels.
- [NEW] `DEVIATIONS-V3.md`: record interpretations, exact diff, D method, and
  verification output.

All persistent files and runtime artifacts stay inside this v3 directory. No
criteria file or v1/v2 validation implementation is copied; validator and
derivation functions are imported from the frozen harness.
