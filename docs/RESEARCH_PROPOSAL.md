# ADIP Research Proposal

Status: frozen before live experiments  
Version: 1  
Date: 2026-09-09  
Hardware scope: one local NVIDIA GeForce RTX 3060 with 12 GB VRAM  

## 1. Working title

ADIP: A Practical Study of Gateway-Level Dynamic Batching for LLM Inference

The title may be revised after analysis, but the paper must remain an empirical
study of external batching and must not claim a new general-purpose inference
engine.

## 2. Problem statement

Inference engines such as vLLM already perform internal continuous batching.
An API gateway may independently collect multiple requests and submit them as
one backend prompt batch. This second scheduling layer can reduce request
overhead, but it can also add queueing delay or interfere with the backend's
own scheduler.

ADIP will measure this interaction on one commodity GPU and evaluate whether a
small adaptive policy can avoid the worst fixed-window decisions.

## 3. Research questions

RQ1. What latency and throughput overhead does ADIP add as a pass-through proxy
compared with direct vLLM access?

RQ2. How do external batch wait time and maximum batch size affect throughput,
end-to-end latency, queue latency, and SLO attainment?

RQ3. Does the answer change under constant-rate, Poisson, and bursty arrivals?

RQ4. Does prompt-length heterogeneity change the best gateway policy?

RQ5. Can a simple policy using queue depth, recent arrival rate, backend
latency, and request slack outperform or match fixed waiting policies?

## 4. Hypotheses

H1. Pass-through ADIP adds measurable but small latency compared with direct
vLLM.

H2. External fixed-window batching improves throughput only in part of the load
range and increases tail latency at low load.

H3. No single fixed wait window is best for every arrival pattern and prompt
distribution.

H4. A simple adaptive policy can avoid unnecessary waiting at low load while
retaining useful batching at high load.

The hypotheses are falsifiable. If an experiment does not support a hypothesis,
the paper must report that result.

## 5. Planned contributions

The paper may make the following contributions if the corresponding evidence
is produced:

1. A controlled characterization of gateway-level batching in front of vLLM.
2. An open-loop, request-level benchmark with GPU telemetry.
3. A simple adaptive batch-closing policy.
4. Practical configuration guidance for a single-GPU external gateway.

## 6. System under study

The system has three local processes:

~~~text
Benchmark client
    |
    +--> direct mode ------> vLLM on port 8001
    |
    +--> gateway modes ----> ADIP on port 8000 ----> vLLM on port 8001
~~~

All processes run on the same Windows machine through WSL2. No cloud endpoint,
remote GPU, or remote inference service is part of the study.

## 7. Models and resource limits

Primary model:

- Qwen/Qwen2.5-1.5B-Instruct.
- Float16.
- Maximum context length: 2,048 tokens.
- Maximum generated tokens: 64.

Secondary validation model:

- Qwen/Qwen2.5-3B-Instruct.
- Float16.
- Same context and output limits unless initialization requires a documented
  reduction.

The RTX 3060 has 12 GB VRAM. If the secondary model cannot run reliably, it
will be omitted and the limitation will be stated. The primary model and all
headline claims must remain reproducible on the RTX 3060.

## 8. Independent variables

- Execution mode:
  - Direct vLLM.
  - ADIP pass-through.
  - ADIP fixed batching.
  - ADIP adaptive batching.
- Offered load:
  - 0.25, 0.50, 0.75, 0.90, and 1.10 times measured direct capacity.
- Arrival process:
  - Constant rate.
  - Poisson.
  - Bursty interval-based rate.
- Prompt distribution:
  - Short.
  - Mixed short, medium, and long.
- Fixed maximum wait:
  - 1, 5, 10, and 20 milliseconds.
- Fixed maximum batch size:
  - 4, 8, and 16 in sensitivity tests.

## 9. Controlled variables

The following must remain fixed inside each comparison:

- Model ID and exact revision.
- vLLM version.
- Python version.
- GPU driver.
- dtype.
- max_model_len.
- gpu_memory_utilization.
- max_num_seqs.
- max_tokens.
- temperature.
- prompt set.
- request arrival schedule.
- random seed.
- warm-up rule.
- run duration.
- cooldown rule.

## 10. Dependent variables

Primary:

- Achieved requests per second.
- Output tokens per second.
- p50, p95, and p99 end-to-end latency.
- SLO attainment percentage.
- Mean and p95 queue latency.

Secondary:

- Mean batch size.
- GPU utilization.
- VRAM usage.
- Power draw.
- Temperature.
- Request failures.
- Harness scheduling drift.

## 11. SLO definition

For each model and workload:

1. Run direct vLLM at 0.25 measured capacity.
2. Calculate p95 end-to-end latency.
3. Define strict SLO as 1.5 times that p95.
4. Define relaxed SLO as 2.0 times that p95.
5. Save the values before final policy comparisons.

The SLO is a soft end-to-end budget. The gateway uses it for dispatch
decisions, but it does not cancel a GPU batch after dispatch. Every completed
request is marked deadline_met=true or false.

## 12. Baselines

The final primary-model comparison must include:

1. Direct vLLM.
2. ADIP pass-through.
3. Best fixed-window ADIP policy selected by the predeclared Pareto rule.
4. Adaptive ADIP policy.

The fixed-window pilot must evaluate 1, 5, 10, and 20 milliseconds before the
best fixed policy is selected.

## 13. Frozen adaptive-policy parameters

Before the final experiments, the adaptive implementation is frozen with the
following settings. These values use only EXP-001 calibration and EXP-002
pilot evidence; EXP-003 and later results must not change them:

- EWMA alpha: `0.2` for arrival-rate and backend-latency estimates.
- Low-load expected-companion threshold: `1.0` request.
- Maximum adaptive wait window: `20` milliseconds, the largest wait evaluated
  in the fixed pilot.
- Maximum batch size: `8`, matching the primary model configuration and fixed
  pilot.
- The adaptive policy dispatches immediately for a full queue, an elapsed
  maximum window, exhausted deadline slack, or low load. Otherwise it waits
  for the minimum of the remaining window, estimated batch-fill time, and
  positive deadline slack.

The selected fixed comparator remains the 1 ms wait from the EXP-002
shortest-nondominated rule. The 20 ms value above is only the adaptive policy's
upper bound, not a claim that 20 ms is the best fixed policy.

## 14. Experimental matrix

Primary final matrix:

- Three workloads.
- Four load levels: 0.25, 0.50, 0.75, 0.90 capacity.
- Four policies: direct, pass-through, best fixed, adaptive.
- Three repetitions.
- 120 seconds of measured traffic per run.

Total primary runs: 3 x 4 x 4 x 3 = 144.

Sensitivity matrix:

- Mixed-Poisson workload.
- 0.50 and 0.90 capacity.
- Wait windows 1, 5, 10, and 20 ms.
- Batch sizes 4, 8, and 16.
- Three repetitions.

Secondary-model validation:

- Short-constant and mixed-bursty workloads.
- 0.50 and 0.90 capacity.
- Direct, pass-through, best fixed, adaptive.
- Three repetitions.

## 15. Arrival and prompt methodology

The benchmark must be open-loop. A request's target arrival time is generated
before execution, and later requests must not wait for earlier requests to
finish.

Prompt text will be generated from project-authored seed passages. The
benchmark records exact tokenizer-derived input token counts. This avoids
redistributing copyrighted prompt corpora while still controlling length.

The prompt mix is:

- 50 percent short: 32 to 128 input tokens.
- 35 percent medium: 129 to 512 input tokens.
- 15 percent long: 513 to 1,024 input tokens.

The final paper must identify this as a synthetic, length-controlled workload
and must not describe it as a production trace.

## 16. Analysis plan

The request is the latency observation unit. The run is the replication unit.
Thousands of requests in one run must not be described as thousands of
independent repetitions.

For each policy and condition:

1. Exclude warm-up records.
2. Keep failed requests in counts.
3. Never convert failure to zero latency.
4. Compute run-level metrics.
5. Aggregate across repetitions.
6. Report 95 percent confidence intervals across run-level values.
7. Plot individual repetition points when only three repetitions exist.

Required comparisons:

- Pass-through minus direct: gateway overhead.
- Fixed batching minus pass-through: batching effect.
- Adaptive minus best fixed: adaptive-policy effect.
- Bursty minus constant: burst sensitivity.

## 17. Exclusion policy

A run may be excluded only for:

- Server crash.
- Harness crash.
- Corrupt result file.
- Configuration mismatch.
- Documented competing GPU workload.
- Missing required instrumentation.

The raw run must remain stored. The exclusion reason and run ID must be
recorded in the experiment log.

## 18. Threats to validity

- One GPU limits hardware generality.
- Two small models do not represent all LLM architectures.
- Synthetic prompts do not represent every production workload.
- vLLM version changes may alter backend scheduling behavior.
- WSL and WDDM may add host-specific effects.
- A soft deadline does not model hard client cancellation.
- External gateway batching may not be beneficial for every backend.

The paper must state these limitations.

## 19. Freeze statement

This proposal freezes the research questions, hypotheses, variables, baselines,
SLO rule, and main matrix before final data collection. Any change must be
recorded in docs/EXPERIMENT_LOG.md with the reason and a new proposal version.
