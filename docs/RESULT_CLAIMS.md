# ADIP Result Claims Ledger

No final numerical claims have been established.

Every numerical or comparative statement in the README, paper, abstract,
conclusion, release notes, or portfolio page must be added here first.

## Claim table

| Claim ID | Claim text | Figure or table | Configurations | Raw run IDs | Status |
| --- | --- | --- | --- | --- | --- |
| EXP-002-EXPL-001 | On the RTX 3060, the corrected ADIP fixed-window pilot formed multi-request batches at 1.8 requests/second; mean batch size was approximately 2.59–3.19 across 1/5/10/20 ms waits. | EXPERIMENT_LOG.md | Qwen 1.5B, short-constant, 1.8 rps, fixed waits | `exp002-fixed-window-pilot-90pct/wait-{1,5,10,20}ms-rate-1p8` | exploratory |
| EXP-002-EXPL-002 | The 1 ms fixed wait was selected by the predeclared shortest-nondominated rule using the 0.50 and 0.90 pilot points. | EXPERIMENT_LOG.md | Qwen 1.5B, short-constant, 0.5 and 1.8 rps, fixed waits | `exp002-fixed-window-pilot/*`, `exp002-fixed-window-pilot-90pct/*` | exploratory |
| EXP-002-NEG-001 | The first pilot attempt was invalid because the batcher failed to drain queued work after a slow backend call; its singleton-batch results are excluded. | EXPERIMENT_LOG.md | Qwen 1.5B, first EXP-002 implementation | `exp002-fixed-window-pilot-attempt-singletons-20260913/*` | exploratory |

## Claim rules

1. A claim must identify the exact raw run IDs that support it.
2. A claim must distinguish pilot from final data.
3. A claim must state the model, workload, offered load, and policy.
4. A percentage must have an absolute baseline value.
5. A headline claim must be supported by at least three repetitions unless it
   is explicitly labeled exploratory.
6. A claim must state when it is limited to the RTX 3060.
7. If a result is neutral or negative, record it rather than omitting it.

## Status values

- pending: not evaluated.
- exploratory: pilot evidence only.
- verified: supported by final runs and audited.
- rejected: contradicted by final runs.
- superseded: replaced by a newer proposal version.
