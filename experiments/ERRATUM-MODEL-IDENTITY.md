# Erratum — model identity across the criteria-matrix runs

Discovered 2026-07-16 by Cedric via the DeepSeek usage dashboard, verified
against the persisted raw API responses (`response.model` field).

## Finding

Every call in the v0/v1/v1-calibration/v2 runs was served by
**`deepseek-v4-flash`**. The requested ids `deepseek-reasoner` and
`deepseek-chat` are aliases: at the v4 era both map to the flash model,
with the `reasoner` alias enabling thinking mode. Verification on raws:

| Run | Requested alias | Served model | reasoning_content |
|---|---|---|---|
| v1 micro-test | deepseek-reasoner | deepseek-v4-flash | 15/15 (~1315 tokens avg) |
| v1 micro-test | deepseek-chat | deepseek-v4-flash | 0/15 |
| v1 calibration | deepseek-reasoner | deepseek-v4-flash | 40/40 (~1250) |
| v2 micro-test | deepseek-reasoner | deepseek-v4-flash | 66/66 (~1610) |

`deepseek-v4-pro` was never used.

## Consequences

- **No result is invalidated.** Every conclusion holds for the
  configuration actually tested — flash with thinking mode ("reasoner"
  alias) vs flash without ("chat" alias) — which was internally consistent
  across all runs. The persisted raws are the authoritative record.
- Wherever run documents say "deepseek-reasoner", read: *the
  deepseek-reasoner alias, served by deepseek-v4-flash with thinking mode*.
  The sealed v1 allowlist ({I1}) is bound to that served configuration.
- **Protocol fix (registered for v3 onward):** harnesses must persist the
  served model per assessment and fail loudly when the served model does
  not match the expected pinned identity. Aliases are moving targets;
  audit trails must name the served model.
