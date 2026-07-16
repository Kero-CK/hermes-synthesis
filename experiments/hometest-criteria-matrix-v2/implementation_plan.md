# Implementation plan — criteria-matrix v2 micro-test

- [MODIFY] `CHARTER.md`: append the pre-implementation schema amendment.
- [NEW] `prompt.txt`: derive from the frozen v1 prompt with exactly the three charter insertions/replacement and the v2 schema rename.
- [NEW] `run_microtest_v2.py`: import the v1 harness, freeze criteria integrity, build blocks A–D, support two replicates, and provide API-free dry-run output.
- [NEW] `analyze_v2.py`: evaluate criteria (a)–(f) offline and emit `v2_report.md`.
- [NEW] `PREREGISTRATION-V2.md`: freeze the exact corpus, D procedure, replicate count, success criteria, and no-post-observation rule.
- [NEW] `test_v2.py`: verify the prompt delta, integrity checks, frozen corpus loading, D refusal, replicate slots, and synthetic criteria logic.
- [NEW] `DEVIATIONS-V2.md`: record only documented interpretations, the exact prompt diff, generation method, and verification outputs.
- [NEW] `blocD.csv`: deterministic five-record proposal with empty labels when the real candidates source is usable.

All runtime artifacts are written below this v2 directory. No criteria file or v1 validation implementation is copied.
