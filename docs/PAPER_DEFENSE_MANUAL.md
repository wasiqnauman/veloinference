# Paper Understanding and Faculty-Defense Manual

## Paper

**Title:** *When Batching Backfires: The Hidden Cost of Adding a Gateway to
Continuous LLM Serving*

This manual is the complete speaking and understanding guide for the paper. It
is intentionally more direct than the manuscript. Read it in this order:

1. Learn the one-sentence claim and the two-minute explanation.
2. Build intuition from the two-scheduler mental model.
3. Learn the experiment and the four comparisons.
4. Memorize the small set of headline numbers.
5. Practice the faculty questions aloud without reading the answers.

Do not present the paper as a new batching algorithm or a production-scale
benchmark. Present it as a controlled empirical systems study that discovers
why an apparently successful outer batch can actually be evidence of harmful
queueing.

## 1. The paper in one sentence

When a serial API gateway batches requests in front of vLLM, the larger batches
can come from requests piling up while the gateway waits for the backend, not
from useful millisecond-scale waiting; in the tested regime, that queueing
increased p95 latency without a consistent backend-time saving.

## 2. The central intuition

There are two schedulers:

1. **The outer scheduler:** ADIP, the HTTP gateway. It decides when requests are
   released and which compatible prompts share one backend HTTP call.
2. **The inner scheduler:** vLLM. It decides which active sequences share GPU
   work at token granularity.

The gateway has less information. It sees requests and completions. vLLM sees
prefill, decode iterations, sequence state, and KV-cache occupancy.

The naive intuition is: "If the gateway reports a larger batch, batching must
be working." The paper shows why that can be false. A serial gateway awaits one
backend call. Requests arriving during that wait cannot reach vLLM, so they
accumulate at the gateway. When the current call finishes, the gateway groups
the backlog into a larger call. The larger group is real, but it was formed by
withholding work from vLLM. It can therefore be a symptom of queueing rather
than an optimization.

### Restaurant analogy

Imagine a kitchen that already combines orders efficiently as they arrive.
Now place a waiter outside the kitchen who collects orders into envelopes. If
the waiter waits one millisecond hoping another customer appears, that wait is
too short to help when customers arrive half a second or more apart. However,
if the waiter is blocked at the kitchen for two seconds, several customers can
line up. The next envelope is larger, but only because those customers were
kept outside. A larger envelope does not prove faster service.

The paper measures exactly this distinction.

## 3. Ready-to-use explanations

### 30-second answer

"I studied a deployment pattern where an API gateway batches prompts before
sending them to vLLM, even though vLLM already continuously batches sequences.
My hypothesis was that, below saturation, millisecond waiting is too short to
form useful batches. Instead, larger gateway batches can emerge because a
serial gateway is blocked on the backend and requests pile up. Across 48 local
conditions and 6,912 requests, fixed outer batching increased p95 latency by
about 1.05 to 1.51 seconds at 1.0 to 1.8 requests per second. A simple occupancy
model predicted the observed outer group sizes with 0.86% mean absolute
percentage error. The contribution is the mechanism: larger outer batches can
measure withheld scheduling opportunity rather than useful batching."

### Two-minute answer

"Modern LLM engines such as vLLM already schedule at token-iteration
granularity. Production systems may still add a gateway that holds requests for
a short window and combines them into one HTTP call. That creates two
schedulers with different information.

I tested whether the outer scheduler actually helps in a controlled,
below-saturation regime. I compared direct vLLM, gateway pass-through, fixed
one-millisecond batching, and a frozen adaptive policy at four request rates
with three repetitions. Arrivals were open loop and periodic, all prompts were
compatible, and every run used the same Qwen2.5-1.5B-Instruct revision on a
single consumer-grade GPU.

The key mechanism is that the scheduled gaps were 556 milliseconds or longer,
so a one-millisecond window could not collect the next scheduled request. Even
the adaptive policy's 20-millisecond cap was much shorter than the gap. Yet
larger groups appeared. They were explained by requests accumulating while the
single gateway coordinator awaited a backend call. The prediction
max(1, arrival rate times backend occupancy) matched measured call-level group
size with 0.86% mean absolute percentage error across 24 batched runs.

At 1.0, 1.5, and 1.8 requests per second, fixed batching increased paired p95
latency by 1,510, 1,047, and 1,370 milliseconds relative to pass-through. The
gateway added roughly 0.77 to 0.83 seconds of mean queueing and backend time did
not improve consistently. I therefore conclude that, in this tested regime, a
larger outer batch was not evidence of useful batching. The default should be
engine-owned scheduling unless an outer layer demonstrates an end-to-end gain."

### One-line contribution statement

The paper turns "double batching may be bad" into a falsifiable mechanism,
measures it with run-level uncertainty, and shows how to distinguish intentional
window batching from backlog coalescing.

## 4. Essential terminology

| Term | Meaning in this paper |
| --- | --- |
| Prefill | Parallel processing of all prompt tokens before generation starts. |
| Decode | Autoregressive generation, usually one new token per active sequence per iteration. |
| Continuous batching | vLLM can admit and retire sequences between decode iterations rather than waiting for a fixed batch to finish. |
| Outer batching | The gateway combines multiple prompts into one backend HTTP call. |
| Double batching | A request-level gateway scheduler is placed in front of an engine that already schedules internally. |
| Pass-through | Requests pass through ADIP one at a time, adding translation and telemetry but no outer batching. |
| Fixed batching | ADIP waits up to 1 ms, with maximum outer batch size 8. |
| Adaptive batching | ADIP uses estimated arrival rate, backend time, queue state, and deadlines, with a 20 ms maximum window. |
| Backlog coalescing | Requests accumulate while the serial gateway awaits the backend and are grouped after it returns. |
| Offered load | The rate at which the open-loop harness schedules requests. |
| p95 latency | The latency value below which 95% of request latencies fall within one run. It is not a confidence interval. |
| 95% confidence interval | Uncertainty over a mean across three run-level repetitions or three paired run-level differences. |
| Replication unit | One complete run, not one request. |
| Compatibility key | Model, output-token cap, and temperature; only equal keys can share an outer call. |
| Coordinated omission | A benchmark error where slow responses suppress later requests, hiding queueing. Open-loop arrivals avoid it. |

## 5. What problem is being studied?

The engineering decision is whether an inference gateway should batch prompts
before sending them to an LLM server that already performs continuous
batching.

Outer batching could help by:

- amortizing HTTP or per-call processing;
- combining prompt work into fewer backend calls;
- reducing backend overhead if the backend benefits from prompt lists.

Outer batching could hurt by:

- intentionally delaying requests;
- preventing vLLM from seeing work as soon as it arrives;
- creating head-of-line blocking in the serial gateway;
- grouping requests with different service times;
- making a request-level policy compete with a better-informed token-level
  policy.

The paper asks not merely which mode is faster, but why the observed batches
form and whether their backend savings repay their queueing cost.

## 6. Hypothesis, null hypothesis, and decision rule

### Research hypothesis

Below saturation, the intentional wait window is too short relative to the
inter-arrival gap to form useful batches. Multi-request outer calls are mainly
formed by backlog accumulated while a serial gateway awaits the backend.
Outer batching helps latency only if the backend-time saving exceeds both the
added gateway queue and the scheduling freedom removed from vLLM.

### Null hypothesis

Fixed and adaptive outer batching provide no repeatable p95-latency advantage
over the appropriate baseline at matched offered load.

### What would have supported useful outer batching?

A convincing positive result would have required all of the following:

1. Larger outer groups.
2. A repeatable reduction in backend time.
3. An end-to-end latency improvement after including gateway queue time.
4. A paired run-level interval supporting that direction.

Only the first item occurred consistently above 0.5 requests/s.

## 7. The two batch-formation mechanisms

### Mechanism A: intentional window formation

Let the offered arrival rate be \(\lambda\) requests/s and the intentional
gateway window be \(w\) seconds.

For the periodic workload, the scheduled gap is:

\[
\Delta = \frac{1}{\lambda}.
\]

If \(w < \Delta\), the next scheduled request cannot arrive during the window
unless there is backlog or abnormal harness delay.

At the highest tested rate:

- \(\lambda = 1.8\) requests/s;
- \(\Delta = 1/1.8 = 0.5556\) s, or 555.6 ms;
- fixed window = 1 ms;
- adaptive cap = 20 ms.

Therefore, intentional waiting alone cannot collect the next periodically
scheduled request. This is stronger than saying that a companion is unlikely.

The paper also gives a Poisson comparison:

\[
E[N_w] = \lambda w, \qquad P(N_w \ge 1) = 1-e^{-\lambda w}.
\]

At 1.8 requests/s, a 1 ms window has only about a 0.18% chance of seeing at
least one companion under memoryless arrivals. A 20 ms window has about a
3.54% chance. This Poisson calculation is intuition only; the confirmatory
experiment used periodic arrivals.

### Mechanism B: backlog formation during service occupancy

Let \(S\) be how long the serial gateway is occupied awaiting one backend call.
Approximately \(\lambda S\) requests can arrive during that time. The next
outer call should therefore have group size near:

\[
\widehat B_{occupancy} = \max(1, \lambda \bar S_{call}).
\]

The floor of one represents the request that starts a new service cycle after
an idle period. The estimate uses mean backend occupancy once per outer call.

This formula is not a queueing theorem for every workload. It is a deliberately
simple diagnostic for a serial worker under this controlled periodic regime.
Its value is that it makes a quantitative, testable prediction that is very
different from the micro-window prediction.

### Why the fit matters

Across all 24 fixed and adaptive runs:

- mean absolute error = 0.020 requests per call;
- mean absolute percentage error = 0.86%;
- descriptive \(R^2 = 0.9985\);
- measured-to-predicted ratios = 0.978 to 1.000.

This is strong consistency with the backlog mechanism. It is not independent
causal proof because measured backend occupancy from each run is used in the
prediction. Say "mechanism-consistency diagnostic," not "causal model."

## 8. System architecture

```text
Open-loop benchmark client
    |
    +--> direct: vLLM on port 8001
    |
    +--> gateway modes: ADIP on port 8000
                              |
                              +--> vLLM on port 8001
                                          |
                                          +--> RTX 3060
```

### The four modes

1. **Direct vLLM:** one client request goes directly to vLLM. This is the
   engine-owned scheduling baseline.
2. **Gateway pass-through:** ADIP adds HTTP translation and telemetry, but each
   request still becomes one backend call. This isolates the cost of merely
   adding the gateway.
3. **Fixed 1 ms:** compatible requests can be grouped up to size 8. Dispatch
   occurs at size 8, after 1 ms, or when deadline slack is exhausted.
4. **Adaptive:** maximum size 8 and maximum window 20 ms. An exponentially
   weighted estimate of arrival rate and backend time is used to close the
   batch early at low load or when deadline slack is limited.

### Why pass-through is the baseline for fixed batching

Comparing fixed batching only with direct vLLM would mix two effects:

- gateway translation and instrumentation;
- the batching policy itself.

Fixed minus pass-through isolates the incremental policy effect. Pass-through
minus direct separately measures the gateway layer.

### Why the coordinator is important

ADIP uses one coordinator that drains compatible queues, dispatches one batch,
and awaits that backend call. This makes the mechanism observable and keeps the
artifact compact, but it also creates the serial-occupancy behavior being
studied. The conclusion therefore applies to this common transparent serial
architecture, not to every possible concurrent or engine-integrated gateway.

## 9. Experiment design

### Hardware and software

- GPU: NVIDIA RTX 3060, 12 GB.
- Host path: Windows with WSL2 Ubuntu.
- Backend: vLLM 0.29.0, eager mode, float16.
- Model: Qwen2.5-1.5B-Instruct.
- Immutable model revision:
  `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`.
- Maximum model length: 2,048 tokens.
- Maximum active sequences: 8.
- vLLM GPU-memory target: 0.85.
- Generation: temperature 0, maximum 64 output tokens.

### Matrix

- Modes: 4.
- Rates: 0.5, 1.0, 1.5, and 1.8 requests/s.
- Repetitions: 3, with seeds 1729, 2718, and 3141.
- Conditions: \(4 \times 4 \times 3 = 48\).
- Measured duration per condition: 120 seconds.
- Total scheduled measurement time: 5,760 seconds, or 96 minutes.
- Warmup: 50 sequential requests per condition, excluded from results.
- Cooldown: 5 seconds between conditions.
- Prompt range: 8 to 128 tokenizer-derived input tokens.
- Measured requests: 6,912.
- Successful requests: 6,912.
- Failed requests: 0.

The request total can be checked directly. Each mode/repetition schedules
\((0.5+1.0+1.5+1.8)\times120=576\) requests. Across four modes and three
repetitions, \(576\times4\times3=6,912\).

### Why periodic arrivals?

Periodic arrivals isolate the batch-formation mechanism. They make it possible
to say exactly whether another scheduled request can fit inside a wait window.
A bursty trace would be more realistic but would mix window formation,
burst-driven backlog, and service-time effects. The paper chooses internal
validity for the mechanism study and explicitly leaves trace realism for
follow-up work.

### Why open-loop arrivals?

The full arrival schedule is generated before execution. Each request waits
until its absolute target time, regardless of whether earlier requests have
finished. A slow server therefore creates visible queueing rather than reducing
the offered load. This avoids coordinated omission.

### Why three repetitions?

Three repetitions were feasible for a 48-condition local matrix and permit a
basic paired uncertainty estimate. They are not enough for precise inference.
The paper therefore shows individual run points, uses Student-t intervals, and
does not treat thousands of requests as independent experimental replications.

### Why pair by seed?

Each treatment and baseline at a rate share the same repetition seed. The
paired difference removes some workload-construction variation. It does not
remove wall-clock or thermal variation because modes were run in fixed order.

### Harness validity gate

The harness records target and actual arrival times. A condition would be
marked `invalid_harness` if more than 1% of requests arrived over 50 ms late.
Such a run would remain on disk but be excluded from performance claims. In the
final matrix, no condition failed this gate; the largest p95 arrival drift was
2.280 ms.

## 10. Metrics and statistical reasoning

### Primary outcome

End-to-end p95 request latency. This captures a tail-latency objective relevant
to interactive serving.

### Supporting metrics

- p50 and p99 end-to-end latency;
- gateway queue time;
- backend time;
- prompts per outer backend call;
- output tokens/s;
- request success and failure counts;
- arrival drift;
- available GPU telemetry, with incomplete samples excluded from claims.

### Request-level observation versus run-level replication

Requests within one run share the same process, machine state, queue, and time
period. They are not independent replications of the entire system condition.
The paper first computes a metric such as p95 within each run, then compares the
three run-level values. This avoids pseudoreplication.

### Paired effects

For a metric \(M\):

\[
\Delta_{proxy}=M_{pass}-M_{direct}
\]

\[
\Delta_{fixed}=M_{fixed}-M_{pass}
\]

\[
\Delta_{adaptive}=M_{adaptive}-M_{fixed}
\]

Positive p95 deltas mean the treatment is slower. Each reported mean paired
effect and interval is computed from three seed-matched run-level differences.

### Why Student-t intervals?

The population variance is unknown and the number of repetitions is three, so
the analysis uses a two-sided Student-t interval with two degrees of freedom.
The critical value is about 4.303, which produces wide intervals. This is a
feature of honest small-sample uncertainty, not an error.

### p95 is not the same as a 95% confidence interval

- p95 describes the tail of request latency within one run.
- A 95% confidence interval describes uncertainty in a mean across runs or
  paired run differences.

Never use these terms interchangeably.

### Call-weighted versus request-weighted batch size

If one backend call contains four requests, its batch-size field appears in
four request records. Averaging those records would count the size-four call
four times and a singleton once. That is size biased.

The analyzer groups records by batch ID and counts each backend call once. This
produces the call-weighted mean outer group size used by the mechanism model.

### Why the throughput column is not capacity

The table's request throughput is successful requests divided by the fixed
120-second arrival schedule. Because the harness waits for outstanding work to
drain and all requests succeed, it equals the offered load. It verifies that
scheduled work completed, but it does not measure maximum service capacity or
include final drain time in the denominator.

## 11. Results you must know

### RQ1: pass-through versus direct

Paired p95 effects in milliseconds:

| Rate | Pass-through minus direct | Interpretation |
| ---: | ---: | --- |
| 0.5 | -180, CI [-676, 317] | Unresolved |
| 1.0 | -451, CI [-1,662, 761] | Unresolved |
| 1.5 | +162, CI [-309, 634] | Unresolved |
| 1.8 | +251, CI [-424, 925] | Unresolved |

Every interval crosses zero. The correct statement is that the experiment did
not resolve a pass-through penalty. Do not say the gateway overhead is zero.

### RQ2: fixed batching versus pass-through

| Rate | Outer group | Pass-through p95 | Fixed p95 | Paired fixed effect | Mean queue |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 1.00 | 1,935 ms | 1,812 ms | -123 ms, CI [-754, 508] | 2 ms |
| 1.0 | 1.54 | 1,884 ms | 3,393 ms | +1,510 ms, CI [1,330, 1,690] | 767 ms |
| 1.5 | 2.24 | 2,172 ms | 3,220 ms | +1,047 ms, CI [303, 1,791] | 788 ms |
| 1.8 | 2.90 | 2,120 ms | 3,490 ms | +1,370 ms, CI [484, 2,256] | 833 ms |

At 0.5 requests/s, calls remain singleton and the effect is unresolved. At
1.0, 1.5, and 1.8 requests/s, all paired intervals for the p95 penalty exclude
zero.

The corresponding means of run-wise relative p95 increases are 82.6%, 48.7%,
and 65.1%.

### Backend-time decomposition

At 1.0, 1.5, and 1.8 requests/s:

| Rate | Pass-through backend mean | Fixed backend mean | Fixed queue mean |
| ---: | ---: | ---: | ---: |
| 1.0 | 1,502 ms | 1,578 ms | 767 ms |
| 1.5 | 1,688 ms | 1,529 ms | 788 ms |
| 1.8 | 1,661 ms | 1,658 ms | 833 ms |

Only the 1.5 requests/s aggregate shows a notable backend-time reduction, and
it is smaller than the added queue. There is no consistent backend saving that
repays the queue.

Do not add the mean queue and mean backend values and compare the result
directly with p95 latency. Means of components and a percentile of total
latency are different statistics. Use the decomposition directionally.

### RQ3: adaptive versus fixed

| Rate | Adaptive minus fixed p95 | Interpretation |
| ---: | ---: | --- |
| 0.5 | +115 ms, CI [-696, 926] | Unresolved |
| 1.0 | -650 ms, CI [-1,669, 369] | Unresolved |
| 1.5 | +216 ms, CI [-1,157, 1,589] | Unresolved |
| 1.8 | -282 ms, CI [-995, 431] | Unresolved |

Every interval crosses zero. The correct claim is that the frozen adaptive
policy did not demonstrate a repeatable advantage. Do not say the policies are
equivalent.

### Mechanism result

The occupancy model's 0.86% mean absolute percentage error is the most
distinctive technical result. It explains why outer group size grew even when
the intentional windows were far shorter than the scheduled gaps.

## 12. How to read every paper visual

### Architecture figure

Point out the two decision boundaries. ADIP controls when and in what HTTP
grouping work becomes visible. vLLM retains token-level control of GPU work.
The direct arrow bypasses ADIP and is essential for isolating the gateway.

### Primary overview figure

- Lines are means across three runs.
- Error bars are run-level 95% Student-t intervals.
- Translucent points are individual runs.
- "Throughput" is the count-normalized completion check, not capacity.
- Outer grouping is call weighted.

The visual story is that fixed batching creates larger outer groups, but the
tail-latency line worsens rather than improves.

### Mechanism figure

- Panel A: measured group size versus the occupancy prediction. Their close
  agreement supports backlog coalescing.
- Panel B: gateway queue stacked above backend time. The visible queue is the
  hidden cost in the title.
- Panel C: paired p95 effects. Positive means the treatment is slower. Fixed
  minus pass-through is clearly positive at 1.0 to 1.8 requests/s; the other
  comparisons remain unresolved.

### Primary table

Use it for absolute p95 baselines, mean group size, queue delay, and the fact
that all offered requests completed. Do not interpret its throughput column as
a saturation test.

### Paired-effects table

Use it for treatment effects. It is stronger than comparing aggregate means
because each treatment run is matched with its baseline by repetition seed.

## 13. What the paper establishes

Within the exact tested configuration, the evidence supports these claims:

1. A transparent pass-through gateway did not have a resolved p95 penalty.
2. Fixed outer batching formed larger calls above 0.5 requests/s.
3. Fixed outer batching increased paired p95 latency at 1.0, 1.5, and 1.8
   requests/s.
4. The added gateway queue was roughly 0.77 to 0.83 seconds in those regimes.
5. Backend time did not decrease consistently enough to repay the queue.
6. Observed outer group size was quantitatively consistent with backlog formed
   during serial backend occupancy.
7. The frozen adaptive policy did not show a repeatable p95 advantage.
8. Request failure and gross arrival-timing error did not explain the result.

## 14. What the paper does not establish

The study does not establish:

- that all gateway batching is harmful;
- that batching fails under bursty traffic;
- maximum vLLM or ADIP capacity;
- behavior under overload;
- results for large models, long contexts, streaming, quantization, tensor
  parallelism, or speculative decoding;
- behavior on native Linux or datacenter GPUs;
- complete GPU-utilization, VRAM, power, or thermal comparisons;
- equivalence between policies whose intervals cross zero;
- independent causal validation of the occupancy equation;
- production-scale generality;
- a public raw dataset, because the traces remain local pending archival
  release.

Being explicit about these boundaries makes the paper more credible.

## 15. Novelty and research contribution

The novelty is not a new batching primitive. It is the combination of:

1. **A precise interaction:** request-level gateway batching in front of
   token-level continuous batching.
2. **A mechanism distinction:** intentional window formation versus backlog
   coalescing during serial service occupancy.
3. **A falsifiable prediction:** the scheduled gap rules out window-formed
   companions, while \(\max(1,\lambda\bar S_{call})\) predicts backlog-formed
   group size.
4. **A controlled comparison:** direct, pass-through, fixed, and adaptive
   modes isolate separate effects.
5. **Auditable negative results:** parameters were frozen, exclusions were
   predeclared, request traces were retained, and final claims map to run IDs.

This is appropriate for a graduate admissions portfolio because it shows how
to turn an engineering intuition into a testable question, design a valid
experiment, discover a mechanism, report uncertainty, and limit claims.

## 16. Relationship to prior systems

- **Orca:** established iteration-level scheduling for generative inference.
  It explains why the inner scheduler already operates below request level.
- **vLLM/PagedAttention:** improves KV-cache management and continuous serving.
  It is the inner engine under test.
- **Clipper:** motivates batching in a general prediction-serving layer. The
  difference is that classical inference often performs a bounded forward
  pass, whereas the LLM backend is itself a stateful scheduler.
- **Sarathi-Serve and DeepSpeed-FastGen:** optimize prefill/decode interaction
  with engine-level visibility that ADIP lacks.
- **DistServe:** separates prefill and decode resources around explicit
  latency objectives.
- **BurstGPT:** motivates future bursty and heterogeneous workload validation.

The gap is the behavior of an outer black-box HTTP batcher when the inner LLM
engine already performs continuous scheduling.

## 17. Implementation map

Use these files if a professor asks where a behavior is implemented:

| Topic | File or function |
| --- | --- |
| Serial coordinator and queues | `gateway/core/batcher.py`, `DynamicBatcher` |
| Fixed closure policy | `gateway/core/policies/fixed.py`, `FixedWindowPolicy.decide` |
| Adaptive closure policy | `gateway/core/policies/adaptive.py`, `AdaptiveWindowPolicy.decide` |
| Compatibility and request metadata | `gateway/core/models.py` |
| vLLM integration | `gateway/backends/vllm.py` and `gateway/clients/backend_http.py` |
| Open-loop timing | `bench/runner.py`, `run_open_loop` |
| Final matrix execution and resume safety | `bench/final.py`, `run_final` and `_load_existing_summary` |
| Frozen matrix | `configs/experiments/primary_final.toml` |
| Run-level analysis and occupancy fit | `bench/analyze_final.py` |
| Machine-readable final evidence | `results/summaries/generated/exp003-analysis.json` |
| Claim-to-run mapping | `docs/RESULT_CLAIMS.md` |
| Tests | `tests/`, currently 89 passing tests |

### Engineering details worth mentioning

- The ingress queue is bounded and rejects cleanly when full.
- Per-key queues are FIFO and only compatible requests batch together.
- Policy objects return pure dispatch decisions; the coordinator owns sleeping
  and mutation.
- Cancellation and shutdown settle queued and in-flight futures exactly once.
- Backend failure resolves every request in the affected outer batch.
- Request records are appended as they complete.
- Summary files are written atomically only after validity checks.
- Complete runs can be safely reused; incomplete directories are rejected
  rather than appended to.

## 18. Faculty question bank

### A. Big-picture questions

#### Q1. What is the research question?

**Short answer:** When does gateway-level batching help or hurt latency when
the backend already performs continuous LLM batching?

**Deeper answer:** I separate the cost of adding a gateway from the incremental
effect of batching, then test whether observed larger outer groups come from
intentional waiting or from backlog accumulated while a serial gateway awaits
the backend.

#### Q2. Why should anyone care?

Inference stacks are layered, and optimization at one layer can conflict with
another. A gateway dashboard may show larger batches and suggest success while
users experience worse tail latency. The paper provides a concrete diagnostic
for that failure mode.

#### Q3. What is the surprising result?

The gateway successfully formed larger batches, but those batches correlated
with substantially worse p95 latency. The batches were explained by serial
occupancy, meaning they were produced by accumulated waiting rather than useful
micro-window coalescing.

#### Q4. What is your main contribution?

The main contribution is the mechanism-level separation of intentional window
batching from backlog coalescing, together with an auditable experiment showing
that the latter can make larger batch size a misleading success metric.

#### Q5. Is this just "queueing adds latency"?

The generic statement is obvious, but it is not enough. The paper identifies
why multi-request batches appear despite windows that cannot capture the next
scheduled arrival, predicts their sizes quantitatively from backend occupancy,
and shows that backend savings fail to offset the measured queue. The research
contribution is the falsifiable decomposition and evidence, not the slogan.

#### Q6. Why call the cost hidden?

Because common monitoring may emphasize outer batch size or backend-call
reduction while ignoring the time requests wait before becoming visible to
vLLM. The queue is visible only when end-to-end timing is decomposed.

#### Q7. Does the title overstate the result?

The title is intentionally memorable, but the subtitle identifies the exact
architectural choice and the abstract limits the claim to the tested regime.
The paper does not claim that all batching backfires. It shows that fixed outer
batching backfired at 1.0 to 1.8 requests/s in this serial design.

### B. Hypothesis and mechanism questions

#### Q8. State the hypothesis precisely.

Below saturation, the intentional gateway window is too short relative to the
arrival gap to create useful groups. Larger groups are mainly backlog formed
while the serial worker awaits the backend. Outer batching improves latency
only if backend-time savings exceed queueing and lost inner-scheduler freedom.

#### Q9. How did you distinguish the two batch mechanisms?

The periodic schedule gives an exact inter-arrival gap. At the highest load the
gap is 555.6 ms, much longer than either the 1 ms fixed window or 20 ms adaptive
cap, so window-only formation cannot explain multi-request calls. I then tested
whether call-weighted group size follows \(\max(1,\lambda\bar S_{call})\), the
requests arriving while the serial worker is occupied. It matched closely.

#### Q10. Why use the floor at one in the occupancy equation?

After an idle period, one request begins the next service cycle even when
\(\lambda S < 1\). The floor prevents the diagnostic from predicting a batch
smaller than the initiating request.

#### Q11. Is \(R^2=0.9985\) causal evidence?

No. Backend occupancy is measured in the same runs and the model is descriptive.
I call it a consistency diagnostic. Causal confidence comes from the design
logic, timing separation, and latency decomposition together, not from \(R^2\)
alone.

#### Q12. Could harness jitter create those batches?

The harness recorded arrival drift. No condition crossed the validity gate,
and the largest condition-level p95 drift was 2.280 ms. That is tiny relative
to the 555.6 ms minimum scheduled gap and cannot explain groups near 2.9.

#### Q13. Why do batches appear at a one-millisecond window if arrivals are far apart?

The one-millisecond timer applies after the serial coordinator is free to
inspect the queue. While it is blocked awaiting the current backend call,
requests can accumulate for roughly the backend service time. The next dispatch
therefore starts with an existing backlog.

### C. Experimental-design questions

#### Q14. Why these four baselines?

Direct measures engine-owned scheduling. Pass-through isolates translation and
instrumentation. Fixed isolates a conventional micro-batching rule. Adaptive
tests whether a modest load-aware closure policy avoids the harm. This sequence
supports clean incremental comparisons.

#### Q15. Why use Qwen2.5-1.5B-Instruct?

It fits reproducibly on the available 12 GB GPU with float16 weights and leaves
room for vLLM's KV cache. The goal is a controlled scheduling study, not a model
quality or maximum-scale result.

#### Q16. Would the result hold for a 70B model?

That is unknown. A larger model changes service time, memory pressure, and the
prefill/decode balance. The mechanism may become stronger because occupancy is
longer, or batching savings may become more valuable. This is a priority for
external validation, not a claim of the current paper.

#### Q17. Why stop at 1.8 requests/s?

The rates were selected from calibration for a below-saturation mechanism
study where direct vLLM could accept all offered work. The experiment was not
designed to estimate maximum capacity or overload behavior.

#### Q18. Why not use a real production trace?

A real trace improves external validity but weakens mechanism isolation because
bursts can form genuine window batches. The periodic matrix is the confirmatory
mechanism experiment. A bursty trace is the correct follow-up study.

#### Q19. Why 120 seconds per condition?

It balances local execution cost with enough arrivals at all four rates for
stable within-run percentiles. Inference uncertainty still comes from three
independent runs, not from treating all requests as independent.

#### Q20. Why 50 warmups?

Warmups reduce startup effects such as model initialization, graph setup,
caches, and first-request overhead. They are sequential and excluded from every
reported aggregate.

#### Q21. Why was the run order not randomized?

The runner used a deterministic recoverable order so interrupted local runs
could be audited and resumed safely. This leaves temporal and thermal drift as
a limitation. A stronger replication would use randomized or blocked
interleaving while preserving immutable run IDs.

#### Q22. Does pairing really control confounding if modes ran at different times?

It controls prompt and workload construction through the shared seed, but it
does not control wall-clock machine state. The paper says this explicitly.
That is why small differences such as pass-through versus direct are treated
as unresolved, while the mechanism also relies on within-run queue, occupancy,
and grouping relationships.

#### Q23. Why use WSL2 rather than native Linux?

The project was constrained to the local machine. WSL2 provided the supported
vLLM path while keeping all experiments local. Host scheduling and the Windows
driver model may affect absolute values, so native-Linux replication is future
work.

#### Q24. How do you know the benchmark did not slow its own arrivals?

It uses an open-loop schedule with absolute target times and records actual
arrival drift. Slow responses do not postpone later scheduled arrivals. The
predeclared drift gate would exclude an overloaded harness.

### D. Statistical questions

#### Q25. Why are 6,912 requests not 6,912 independent samples?

Requests in one run share system state, queues, code, temperature, and time.
Treating them as independent would produce artificially narrow intervals. The
run is the replication unit, so inferential comparisons use three paired run
differences.

#### Q26. Are three repetitions enough?

They are enough to expose the large fixed-batching penalty and support a modest
portfolio study, but not enough for precise general inference. The wide t
intervals show this honestly. More randomized repetitions are the clearest
statistical improvement.

#### Q27. Why not use a bootstrap?

With only three independent runs, resampling requests would be
pseudoreplication and resampling three runs provides little additional
information. A t interval is transparent about the small number of degrees of
freedom. More run-level repetitions matter more than a more elaborate method.

#### Q28. Why use p95 instead of mean latency?

Interactive systems care about tail latency, and queueing often appears first
in the tail. Mean queue and backend times are still reported for mechanism
decomposition, but p95 is the primary user-facing outcome.

#### Q29. Why not report statistical significance?

The paper reports effect directions and intervals instead of turning a very
small run count into binary significance claims. When an interval excludes
zero, I say the observed paired penalty is resolved within the tested matrix.
When it crosses zero, I say unresolved, not equal.

#### Q30. Why are some confidence intervals so wide?

There are only three run-level observations and the two-degree-of-freedom t
critical value is large. The wide intervals correctly express run-to-run
uncertainty.

#### Q31. Why does the table show zero-width throughput intervals?

The metric is successful requests divided by the fixed scheduled duration. All
scheduled requests succeeded at every rate, so it mechanically equals offered
load. It is a completion check, not an independently measured service rate.

### E. Result-interpretation questions

#### Q32. What is the strongest numerical result?

Fixed versus pass-through increased paired p95 latency by 1,510 ms at 1.0
requests/s, 1,047 ms at 1.5, and 1,370 ms at 1.8; all three intervals exclude
zero. The mechanism fit is the strongest explanatory result: 0.86% MAPE over
24 batched runs.

#### Q33. Why was fixed p95 lower at 0.5 requests/s?

The mean difference was -123 ms, but its interval was [-754, 508] ms. Calls
were singleton and the effect is unresolved. It should not be presented as a
benefit.

#### Q34. Why did pass-through sometimes look faster than direct?

Run-to-run variation and fixed execution order can create mean differences in
either direction. Every pass-through interval crossed zero, so the data do not
resolve the gateway layer's latency effect.

#### Q35. Did batching increase throughput?

This experiment cannot answer that. Every mode completed the offered schedule,
and the displayed request rate uses the schedule duration rather than the full
drain time. A saturation sweep with completion-time or goodput accounting is
needed for capacity claims.

#### Q36. Did batching reduce backend time?

Not consistently. At 1.5 requests/s it reduced the aggregate mean backend time
from 1,688 to 1,529 ms, but added 788 ms of mean queueing. At 1.0 it increased
backend time, and at 1.8 it was nearly unchanged.

#### Q37. Why can mean queue plus mean backend differ from p95 total latency?

The first two are means of components, while the latter is a percentile of the
per-request sum. Percentiles are nonlinear, so those quantities are not
algebraically interchangeable.

#### Q38. Did the adaptive algorithm fail?

It did not demonstrate a repeatable p95 advantage over fixed batching in this
matrix. That is narrower than saying it failed universally. Its low-load
bypass could reduce intentional waiting, but it could not undo backlog already
formed while the serial worker awaited the backend.

#### Q39. Why not tune the adaptive policy on the final results?

That would overfit the confirmatory matrix. The policy was frozen from pilot
work before final evaluation. A new policy should be proposed and tested on a
new matrix.

#### Q40. Could the result just be a bug in ADIP?

The serial awaiting behavior is intentional and documented, not an accidental
leak. The artifact has unit and integration tests, explicit failure semantics,
and 89 passing tests. More importantly, queue, backend occupancy, batch IDs,
and end-to-end latency agree quantitatively with the predicted serial mechanism.
A concurrent implementation would be a different design and a valuable next
comparison.

### F. Scope and limitation questions

#### Q41. What is the biggest limitation?

External validity: one small model, one consumer GPU, WSL2, short synthetic
prompts, periodic arrivals, four below-saturation rates, and three repetitions.
The paper gives a strong local mechanism result, not a universal deployment
law.

#### Q42. Why is GPU telemetry absent from the conclusions?

After a restart, 738 of 5,726 GPU-monitor samples recorded
`FileNotFoundError`, leaving incomplete adaptive coverage. Request, queue,
backend, batch, failure, and arrival data remained complete, but the paper
correctly excludes comparative GPU claims.

#### Q43. Could thermal drift explain the fixed-batching result?

Fixed order means slow drift cannot be completely ruled out. However, the
fixed-batching penalties are large, the gateway queue is directly measured,
and observed group size tracks same-run backend occupancy. A randomized
interleaved replication is still needed to strengthen causal confidence.

#### Q44. What if arrivals are bursty?

Then intentional windows may capture real companions, so outer batching may
have a different trade-off. The current periodic result provides a clean
baseline and predicts that the relevant comparison remains backend savings
versus added queue and lost inner-scheduler freedom.

#### Q45. What if the gateway sends concurrent backend calls?

Concurrency would reduce or alter serial backlog formation and expose arrivals
to vLLM sooner. It is one of the most important alternative designs to test.
The current conclusion is explicitly tied to one serial coordinator.

#### Q46. What if requests stream tokens?

The completions experiment measures full request latency, not time to first
token or inter-token latency. A streaming study should measure TTFT and
time-per-output-token because outer waiting can harm TTFT even when total
completion behaves differently.

#### Q47. Why are raw traces not public yet?

They remain local until a clean archival release is prepared with allowable
records, environment details, checksums, and permanent hosting. The manuscript
does not falsely claim a public dataset.

### G. Research-process and ownership questions

#### Q48. What did you personally learn?

"I learned that system metrics need mechanism checks. I initially treated
larger batches as a likely optimization signal, but the arrival math showed
that the configured window could not have formed them. That forced me to
instrument queue and backend time, use call-weighted grouping, and test the
serial-occupancy explanation. I also learned to separate request observations
from run-level replication and to report unresolved results honestly."

#### Q49. What would you do first with more compute?

Run randomized, interleaved repetitions on native Linux across a larger model
and longer-context workload, then add bursty traces. This directly tests
generalization while preserving the current four-mode ablation.

#### Q50. What would you change in the system design?

Compare the serial coordinator with a bounded-concurrency gateway and an
engine-aware policy. The goal would be to expose work to vLLM promptly while
retaining gateway admission control and observability.

#### Q51. What result would falsify your explanation?

If multi-request groups appeared when both scheduled gaps and measured service
occupancy were too short to account for them, or if group size systematically
exceeded the occupancy prediction, then intentional waiting, harness behavior,
or another queueing source would be needed. A concurrent gateway showing large
beneficial groups without queue growth would also limit the serial explanation.

#### Q52. Is a negative result publishable?

Yes, if it is a well-scoped, reproducible boundary with a mechanism. The paper
does not merely say an optimization failed. It explains why the success metric
was misleading and provides a decision rule for when outer batching should be
considered.

## 19. Hard questions and safe answers

### "Your title sounds universal."

"The title names the failure mode, while the abstract and conclusion restrict
it to a serial outer gateway in the measured below-saturation regime. I would
not claim that every form of batching backfires."

### "The occupancy model is almost tautological."

"It uses measured service occupancy, so I agree it is not independent causal
evidence. Its purpose is diagnostic: the periodic schedule rules out the
micro-window as the source of companions, and the occupancy estimate tests
whether the serial backlog is quantitatively sufficient. The paper labels the
fit descriptive and combines it with direct queue measurements and paired
latency effects."

### "Three runs are too few."

"They limit precision, which is why I use run-level t intervals, show every run
point, and call several comparisons unresolved. The fixed penalty remains large
enough for all three relevant intervals to exclude zero, but a stronger paper
would add randomized repetitions."

### "Why should this be a paper instead of a blog post?"

"The work has a falsifiable hypothesis, controlled baselines, predeclared
validity rules, run-level uncertainty, a quantitative mechanism prediction,
and auditable claim-to-run provenance. Its contribution is a reproducible
systems result, not only an engineering opinion."

### "Are you claiming causality?"

"I claim mechanism-consistent evidence within a controlled implementation. I
do not claim universal causality. Fixed order, same-run occupancy, and a single
system configuration are explicit threats to causal generalization."

### "Could batching still improve throughput at saturation?"

"Yes. This study deliberately stays below saturation and cannot estimate
capacity. Saturation and goodput are separate follow-up questions."

### "Why did you not hide the telemetry failure?"

"Because reproducibility includes negative evidence about the measurement
process. The request-level data needed for the primary claims are complete, but
the missing GPU samples make utilization comparisons unsupported, so I removed
them from paper-facing claims."

## 20. Five-minute presentation structure

### Slide or minute 1: Problem

"vLLM already batches continuously. What happens when a gateway batches again?"

Draw client -> ADIP -> vLLM -> GPU, plus a direct client -> vLLM arrow.

### Slide or minute 2: Hypothesis

Draw two timelines:

```text
Intentional window:  |--1 ms--|                    next arrival at >=556 ms
Serial occupancy:    |--------- backend call ~1.5 s ---------|
Arrivals:            x              x              x
```

Explain that the first timeline cannot form the observed groups, while the
second can.

### Slide or minute 3: Experiment

State four modes, four rates, three repetitions, 48 conditions, 6,912 requests,
open-loop periodic arrivals, and a single consumer-grade GPU.

### Slide or minute 4: Results

Say only the essential numbers:

- outer group size 1.54 to 2.90 above 0.5 requests/s;
- fixed p95 penalty 1.05 to 1.51 seconds;
- added queue 0.77 to 0.83 seconds;
- occupancy-model error 0.86%;
- adaptive advantage unresolved.

### Slide or minute 5: Meaning

"A larger gateway batch can be a queueing symptom. Measure end-to-end latency
and mechanism, not batch size alone. Let the engine own scheduling unless the
outer layer proves that backend savings exceed its queue."

End with the strongest limitation and next experiment: randomized bursty
native-Linux replication with a larger model and a concurrent gateway.

## 21. Whiteboard derivation to practice

1. Write \(\lambda=1.8\) requests/s.
2. Compute \(\Delta=1/\lambda=0.5556\) s = 555.6 ms.
3. Compare \(w=1\) ms and adaptive cap 20 ms with \(\Delta\).
4. Conclude that periodic window formation predicts singleton calls.
5. Write \(\widehat B=\max(1,\lambda\bar S_{call})\).
6. Use an illustrative \(\bar S_{call}\approx1.6\) s:
   \(1.8\times1.6\approx2.88\), close to the observed 2.90 fixed group size.
7. Explain that the group is formed while the worker is occupied, not during a
   one-millisecond collection window.

Label the 1.6-second value as an illustration near the measured call occupancy,
not a new independently reported estimate.

## 22. Number sheet to memorize

| Item | Number |
| --- | ---: |
| Conditions | 48 |
| Measured requests | 6,912 |
| Request failures | 0 |
| Harness-invalid final conditions | 0 |
| Rates | 0.5, 1.0, 1.5, 1.8 requests/s |
| Repetitions | 3 |
| Fixed window | 1 ms |
| Adaptive cap | 20 ms |
| Maximum outer batch | 8 |
| Minimum scheduled gap | 555.6 ms |
| Fixed outer groups above 0.5 rps | 1.54, 2.24, 2.90 |
| Fixed paired p95 penalties | 1,510, 1,047, 1,370 ms |
| Fixed mean queues | 767, 788, 833 ms |
| Occupancy MAPE | 0.86% |
| Occupancy descriptive R-squared | 0.9985 |
| Largest p95 arrival drift | 2.280 ms |
| Passing repository tests | 89 |

## 23. Phrases to use and avoid

### Use

- "Within the tested single-GPU regime..."
- "The paired interval excludes zero."
- "The experiment did not resolve this difference."
- "Mechanism-consistent evidence."
- "Call-weighted prompts per backend call."
- "Count-normalized completion check."
- "The frozen policy did not demonstrate a repeatable advantage."
- "The result motivates, rather than replaces, broader validation."

### Avoid

- "Gateway batching is always bad."
- "We proved causality."
- "The adaptive policy is equivalent to fixed."
- "Throughput was identical."
- "The study has 6,912 independent samples."
- "The 0.9985 R-squared proves the model."
- "There was no gateway overhead."
- "GPU utilization was unchanged."
- "The artifact is fully public" until raw traces are archived.

## 24. Best next experiments

Rank future work in this order:

1. Randomized, blocked, interleaved execution with at least 10 repetitions.
2. Bursty and heterogeneous arrivals while preserving the four-mode ablation.
3. A bounded-concurrency gateway to break the serial-occupancy mechanism.
4. Native Linux replication with complete GPU telemetry.
5. Larger models and longer prompt/output distributions.
6. Streaming metrics: time to first token and time per output token.
7. Saturation sweeps using completion span, goodput, and latency SLOs.
8. Engine-aware coordination using token-level or queue-state feedback.
9. Public archival release with raw traces, manifests, environment lockfiles,
   checksums, and a permanent DOI.

## 25. Final self-test

You are ready to discuss the paper when you can answer all of these without
looking:

1. Why can a larger outer batch be harmful?
2. Why can the one-millisecond window not explain the observed groups?
3. What does \(\max(1,\lambda\bar S_{call})\) represent?
4. Why is the occupancy fit not causal proof?
5. Why compare fixed with pass-through rather than only with direct?
6. Why are there three inferential samples per condition rather than hundreds?
7. What is the difference between p95 latency and a 95% confidence interval?
8. Why is the throughput column not a capacity result?
9. Which fixed-policy intervals exclude zero?
10. Why is the adaptive result "unresolved" rather than "equivalent"?
11. What is the strongest limitation?
12. What experiment would most directly strengthen the result?

If you can explain the restaurant analogy, derive the 555.6 ms gap, state the
three fixed p95 penalties, explain the 0.86% occupancy fit honestly, and name
the main limitations before being prompted, you have the right intuition and
defense posture for a faculty discussion.
