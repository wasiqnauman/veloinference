# ADIP Result Claims Ledger

Final EXP-003 claims were established from the audited 48-condition matrix on
2026-09-19. The machine-readable source is
`results/summaries/generated/exp003-analysis.json`.

Every numerical or comparative statement in the README, paper, abstract,
conclusion, release notes, or portfolio page must be added here first.

## Claim table

| Claim ID | Claim text | Figure or table | Configurations | Raw run IDs | Status |
| --- | --- | --- | --- | --- | --- |
| EXP-002-EXPL-001 | On the RTX 3060, the corrected ADIP fixed-window pilot formed multi-request batches at 1.8 requests/second; mean batch size was approximately 2.59–3.19 across 1/5/10/20 ms waits. | EXPERIMENT_LOG.md | Qwen 1.5B, short-constant, 1.8 rps, fixed waits | `exp002-fixed-window-pilot-90pct/wait-{1,5,10,20}ms-rate-1p8` | exploratory |
| EXP-002-EXPL-002 | The 1 ms fixed wait was selected by the predeclared shortest-nondominated rule using the 0.50 and 0.90 pilot points. | EXPERIMENT_LOG.md | Qwen 1.5B, short-constant, 0.5 and 1.8 rps, fixed waits | `exp002-fixed-window-pilot/*`, `exp002-fixed-window-pilot-90pct/*` | exploratory |
| EXP-002-NEG-001 | The first pilot attempt was invalid because the batcher failed to drain queued work after a slow backend call; its singleton-batch results are excluded. | EXPERIMENT_LOG.md | Qwen 1.5B, first EXP-002 implementation | `exp002-fixed-window-pilot-attempt-singletons-20260913/*` | exploratory |
| EXP-003-VAL-001 | All 48 planned conditions completed. Across 6,912 measured requests, 6,912 succeeded and zero failed. No run exceeded the predeclared drift gate; the largest p95 arrival drift was 2.280 ms. | Analysis JSON; primary table | All final configurations | `direct-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `pass_through-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `fixed-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `adaptive-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}` | verified |
| EXP-003-PROXY-001 | The pass-through gateway's paired p95-latency deltas relative to direct vLLM were -180, -451, +162, and +251 ms at 0.5, 1.0, 1.5, and 1.8 requests/s. Every 95% Student-t interval crossed zero, so this experiment does not resolve a pass-through penalty. | Paired-effects table; mechanism Figure C | Direct and pass-through, all final rates, three paired repetitions | `direct-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `pass_through-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}` | verified |
| EXP-003-BATCH-001 | At 0.5 requests/s, fixed batching formed singleton calls (mean 1.00) and changed paired p95 latency by -123 ms with a 95% interval of [-754, +508] ms relative to pass-through. The low-load effect is unresolved. | Primary table; paired-effects table | Fixed 1 ms and pass-through, 0.5 requests/s, three paired repetitions | `fixed-rate-0p5-rep-{1,2,3}`; `pass_through-rate-0p5-rep-{1,2,3}` | verified |
| EXP-003-BATCH-002 | At 1.0 requests/s, fixed 1 ms batching increased paired p95 latency by 1,510 ms, 95% interval [1,330, 1,690]. The mean run-wise paired relative increase was 82.6%; the aggregate pass-through mean was 1,884 ms. Mean outer group size was 1.54 and mean gateway queue delay was 767 ms. | Primary table; paired-effects table; overview figure | Fixed 1 ms and pass-through, 1.0 requests/s, three paired repetitions | `fixed-rate-1p0-rep-{1,2,3}`; `pass_through-rate-1p0-rep-{1,2,3}` | verified |
| EXP-003-BATCH-003 | At 1.5 requests/s, fixed 1 ms batching increased paired p95 latency by 1,047 ms, 95% interval [303, 1,791]. The mean run-wise paired relative increase was 48.7%; the aggregate pass-through mean was 2,172 ms. Mean outer group size was 2.24 and mean gateway queue delay was 788 ms. | Primary table; paired-effects table; overview figure | Fixed 1 ms and pass-through, 1.5 requests/s, three paired repetitions | `fixed-rate-1p5-rep-{1,2,3}`; `pass_through-rate-1p5-rep-{1,2,3}` | verified |
| EXP-003-BATCH-004 | At 1.8 requests/s, fixed 1 ms batching increased paired p95 latency by 1,370 ms, 95% interval [484, 2,256]. The mean run-wise paired relative increase was 65.1%; the aggregate pass-through mean was 2,120 ms. Mean outer group size was 2.90 and mean gateway queue delay was 833 ms. | Primary table; paired-effects table; overview figure | Fixed 1 ms and pass-through, 1.8 requests/s, three paired repetitions | `fixed-rate-1p8-rep-{1,2,3}`; `pass_through-rate-1p8-rep-{1,2,3}` | verified |
| EXP-003-MECH-001 | Across all 24 fixed and adaptive runs, the serial-occupancy prediction had 0.020 requests/call mean absolute error, 0.86% mean absolute percentage error, descriptive R-squared 0.9985, and measured-to-predicted ratios from 0.978 to 1.000. This is a consistency diagnostic using measured backend occupancy, not independent causal proof. | Analysis JSON; mechanism Figure A | Fixed 1 ms and adaptive 20 ms cap, all final rates and repetitions | `fixed-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `adaptive-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}` | verified |
| EXP-003-ADAPT-001 | Adaptive batching did not produce a resolved p95-latency improvement over fixed batching at any tested rate. Paired mean deltas were +115, -650, +216, and -282 ms, and all 95% intervals crossed zero. | Paired-effects table; mechanism Figure C | Adaptive 20 ms cap and fixed 1 ms, all final rates, three paired repetitions | `adaptive-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}`; `fixed-rate-{0p5,1p0,1p5,1p8}-rep-{1,2,3}` | verified |
| EXP-003-METRIC-001 | All scheduled requests completed, making the count-normalized throughput metric equal the offered rate in every cell. Because it divides successful request count by the fixed schedule duration rather than observed completion span, it must not be presented as an independent capacity or saturation result. | Analysis JSON; primary table | All final configurations | All 48 EXP-003 run IDs listed in EXP-003-VAL-001 | verified |
| EXP-003-LIMIT-001 | Complete-matrix GPU comparisons are not supported. Of 5,726 GPU-monitor samples, 738 recorded `FileNotFoundError` after restart, leaving only one or two adaptive repetitions with telemetry at some rates. | Progress audit; raw `gpu.jsonl` artifacts | All final configurations | All 48 EXP-003 run IDs listed in EXP-003-VAL-001 | verified |

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
