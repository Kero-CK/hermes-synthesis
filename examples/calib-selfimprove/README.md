# Calibration example — self-improving-agents gold set

This is a real run of the `sysrev-calibrate` skill, kept as a worked example. It's not a demo built for the README — it's the actual output from calibrating the screening step before using it on a live review.

## What's here

- **`protocol.md`** — the review protocol (question, inclusion/exclusion criteria, extraction codebook) for a scoping review on self-improving LLM agents.
- **`candidates.csv`** — the corpus the gold set was drawn from: real OpenAlex records, retrieved and deduplicated by the pipeline.
- **`gold_set.csv`** — 24 articles hand-labelled `include`/`exclude` against the protocol above: 12 `exclude` (fine-tuning / weight-retraining methods, which the protocol explicitly excludes) and 12 `include` (self-improving agents that adapt at inference/deployment time, which the protocol targets).
- **`calibration.json`** — the output of `sysrev-calibrate`: metrics at the default thresholds, plus a small menu of alternative threshold pairs.

## Results

At the tool's default thresholds (include ≥ 0.75, exclude ≤ 0.25):

- **Recall: 91.7%** (11/12 true includes caught)
- **Precision: 91.7%** (11/12 flagged includes were correct)
- **Cohen's κ: 0.83** (near-perfect agreement between the LLM screener and the gold labels)
- 1 false positive, 1 false negative, 0 ambiguous cases at these thresholds

## What this validates — and what it doesn't

This confirms the `sysrev-calibrate` skill works end-to-end: it reads a gold set, scores it against a protocol, computes recall/precision/F1/κ, and proposes threshold trade-offs. On a corpus built around two conceptually distinct categories (fine-tuning vs. inference-time adaptation), the screener separates them well.

That's a **functional validation of the tool on clear-cut cases** — it is **not** a representative research-grade recall calibration, and I don't want to overstate it. Specifically:

- **The gold set was assembled by provenance, not blind labelling.** I built the two classes by querying OpenAlex for terms that already lean toward one category or the other (e.g. "fine-tuning" vs. "self-improving agent"), then labelled by inspection. A researcher doing a real calibration would sample from the full retrieved corpus and label blind, without knowing which query surfaced each record.
- **Data leakage risk, assumed openly.** The `include` labels come from articles that had already been screened as relevant earlier in this same project's pipeline. I have not re-run this calibration on articles the screening model has never seen, so I can't rule out the model doing better here than it would on a genuinely unseen corpus.
- **The gold set is small and the split is easy.** 24 articles across two well-separated categories is enough to sanity-check the mechanism, not enough to estimate recall with any statistical confidence, and not enough to catch the model's failure modes on genuinely ambiguous or borderline articles — which is where screening calibration actually matters.

A real recall calibration — the kind that would let a researcher trust the screening step on a novel domain — still needs to be done by someone running this on articles the model has never scored before, with blind labelling from the retrieved corpus itself. This example is a checkpoint on the way there, not a substitute for it.

## Reproducing this

To reproduce: run `sysrev-calibrate` against `gold_set.csv` in a review folder containing `protocol.md` (both included here). The skill re-scores the gold set against the protocol's criteria and recomputes `calibration.json` from scratch.
