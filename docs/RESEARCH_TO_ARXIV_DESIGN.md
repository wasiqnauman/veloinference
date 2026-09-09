# ADIP Research-to-arXiv Design and Execution Specification

Status: normative execution plan  
Baseline branch: main  
Baseline commit: 81ac3224ecbdf3c22c4b0b675d156e945598efa0  
Primary machine: Windows host with one NVIDIA GeForce RTX 3060, 12 GB VRAM  
Primary execution environment: Ubuntu 24.04 under WSL2, stored on the D: drive  
Primary paper category target: arXiv cs.DC; consider cs.LG as a cross-list  

## 1. Purpose

This document is the authoritative implementation and research plan for turning
the current ADIP prototype into:

1. A correct single-GPU inference gateway.
2. A reproducible open-loop benchmarking artifact.
3. An empirical study of gateway-level dynamic batching in front of vLLM.
4. A modest adaptive batching policy.
5. A complete LaTeX research paper suitable for submission as an arXiv
   preprint.

The intended audience is coding agents that may have no prior knowledge of the
repository. Agents MUST follow the phases in order unless a task explicitly
states that it can run in parallel. Agents MUST NOT invent broader project
goals, change the research question, or add unrelated infrastructure.

This is a research-capability project. It is not intended to claim that ADIP
invented dynamic batching or that it outperforms all production serving
systems. The final claims MUST be limited to observations supported by the
experiments conducted on the specified local machine.

## 2. Normative language

The words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY have the following
meanings:

- MUST: required for the task or phase to be complete.
- MUST NOT: prohibited because it threatens correctness, reproducibility, or
  scope.
- SHOULD: expected unless the agent records a concrete reason not to do it.
- SHOULD NOT: avoid unless required to unblock a MUST.
- MAY: optional and must not delay required work.

## 3. Fixed research framing

### 3.1 Working title

ADIP: A Practical Study of Gateway-Level Dynamic Batching for LLM Inference

The title MAY change after results are known, but only to make the claim more
accurate. It MUST NOT become more ambitious than the evidence.

### 3.2 Research problem

Modern LLM inference engines such as vLLM already perform internal continuous
batching. An external API gateway may also collect multiple independent HTTP
requests and submit them as one prompt batch. This creates two scheduling
layers. The effect of this gateway-level batching depends on offered load,
prompt length, output length, batching window, and the backend's own scheduler.

The project studies when external batching helps, when it hurts, and whether a
small adaptive policy can avoid the worst fixed-window choices.

### 3.3 Research questions

RQ1. What overhead does ADIP add when operating as a pass-through proxy?

RQ2. How do gateway batch wait time and maximum batch size affect throughput,
end-to-end latency, queue latency, and SLO attainment in front of vLLM?

RQ3. How do steady, Poisson, and bursty arrivals change the answer to RQ2?

RQ4. How does prompt-length heterogeneity change the answer to RQ2?

RQ5. Can a simple queue-, arrival-rate-, and deadline-aware policy match the
throughput of the best fixed policy while reducing latency penalties when load
changes?

### 3.4 Provisional hypotheses

These hypotheses MUST be written into the research proposal before final
experiments. They MUST NOT be rewritten after final results are observed.

- H1: ADIP pass-through adds measurable but small overhead relative to direct
  vLLM.
- H2: Fixed gateway batching improves throughput only in part of the load
  range and increases tail latency at low load.
- H3: No single fixed wait window is best for every arrival process and prompt
  distribution.
- H4: A simple adaptive policy can avoid unnecessary waiting at low load while
  retaining useful batching at high load.

If a hypothesis is not supported, the paper MUST report that result. A
negative result is acceptable. Cherry-picking configurations is prohibited.

### 3.5 Planned contributions

The final paper may claim only contributions supported by completed artifacts:

1. A reproducible characterization of gateway-level batching in front of an
   already batching LLM engine.
2. An open-loop benchmark that records request-level and GPU-level evidence.
3. A simple adaptive batch-closing policy.
4. Practical guidance for configuring an external inference gateway on
   commodity single-GPU hardware.

### 3.6 Non-goals

Agents MUST NOT add the following before the arXiv milestone:

- Multi-GPU or multi-node scheduling.
- Kubernetes, autoscaling, or service discovery.
- Custom CUDA kernels.
- Training or fine-tuning models.
- A learned scheduling policy.
- Formal optimality proofs.
- Streaming generation unless TTFT measurement is explicitly promoted to a
  required metric after the first pilot.
- Triton integration.
- gRPC implementation from the existing proto file.
- A web frontend.
- Authentication, billing, or user management.
- More than two model families.
- Production dashboard infrastructure.

## 4. Current repository state

The baseline repository is a phase-one Python prototype.

Implemented:

- FastAPI application lifecycle.
- GET /health.
- POST /v1/infer.
- One asyncio queue.
- A fixed-window DynamicBatcher.
- A synthetic MockBackend.
- A small closed-loop benchmark.
- Seven tests, of which two require pytest-asyncio.

Present but empty or incomplete:

- gateway/backends/vllm.py
- gateway/backends/triton.py
- gateway/clients/backend_http.py
- gateway/observability/logging.py
- gateway/observability/metrics.py
- bench/plot_results.py
- README.md

Known correctness or research limitations:

- The current app always constructs MockBackend.
- The model request field does not select a backend.
- Different model values can enter the same batch.
- deadline_ms is not a complete scheduling or timeout semantic.
- PendingRequest.future is typed as object.
- Cancelling the batch worker during backend execution can leave local batch
  futures unresolved.
- The current benchmark is closed-loop and can hide overload.
- The current percentile implementation is not suitable for publication.
- The Dockerfile invokes uv without installing it.
- The project requires Python 3.14 although the local supported vLLM setup will
  use Python 3.12.
- There is no dependency lock on main.
- The protobuf definition is unused.

Agents MUST preserve this list as baseline context. Fixes must be tied to a
task in this specification.

## 5. Hardware and environment contract

### 5.1 Verified host facts

- GPU: NVIDIA GeForce RTX 3060.
- VRAM: 12,288 MiB.
- Driver: 596.49.
- Driver-reported CUDA capability: 13.2.
- Host Python: 3.13.4.
- Host uv: 0.10.4.
- WSL: not installed at baseline.
- Docker: not installed at baseline.
- C: free space at baseline: approximately 4.2 GB.
- D: free space at baseline: approximately 65.7 GB.

### 5.2 Required local topology

Use three local processes:

~~~text
Open-loop benchmark client
    |
    | direct mode: http://127.0.0.1:8001
    | gateway modes: http://127.0.0.1:8000
    v
ADIP gateway on port 8000
    |
    v
vLLM OpenAI-compatible server on port 8001
    |
    v
RTX 3060 GPU
~~~

All three processes MUST run on the same physical machine. Network calls MUST
use loopback. No cloud inference endpoint may be used.

### 5.3 Required WSL setup

WSL installation requires administrator access and may require a reboot. A
coding agent MUST NOT pretend this step succeeded without verifying it.

Run in administrator PowerShell:

~~~powershell
wsl --list --online
wsl --install --distribution Ubuntu-24.04 --location D:\WSL\Ubuntu-24.04
~~~

If Ubuntu-24.04 is not the exact listed distribution name, use the exact Ubuntu
24.04 name returned by wsl --list --online. Do not substitute another
distribution silently.

After reboot, verify:

~~~powershell
wsl -l -v
~~~

Expected evidence:

~~~text
NAME             STATE    VERSION
Ubuntu-24.04     ...      2
~~~

Inside WSL, verify:

~~~bash
nvidia-smi
~~~

Expected evidence:

- The NVIDIA GeForce RTX 3060 is listed.
- Total memory is approximately 12 GB.
- The command exits successfully.

Stop condition:

If nvidia-smi does not work inside WSL, stop. Do not install vLLM or modify
application code. Record the exact command output and resolve GPU passthrough
first.

### 5.4 Storage placement

The WSL distribution MUST reside on D:. The Linux repository MUST be cloned or
copied to:

~~~text
~/src/veloinference
~~~

Do not run experiments from /mnt/c because C: has insufficient free space and
mounted Windows filesystem performance can distort measurements.

The following directories MUST remain inside the WSL ext4 virtual disk:

~~~text
~/src/veloinference
~/.cache/huggingface
~/.cache/uv
~/venvs
~~~

Before downloading a model, verify at least 20 GB remains available to WSL.

### 5.5 Python environments

Use two environments to avoid vLLM dependency conflicts:

1. Gateway and benchmark environment: repository-local .venv managed by uv.
2. vLLM server environment: ~/venvs/adip-vllm managed by uv.

Both environments SHOULD use Python 3.12.

The gateway project's .python-version MUST contain:

~~~text
3.12
~~~

vLLM MUST be pinned to an exact tested version in requirements/vllm.txt. Do
not use an unpinned latest dependency in final experiments.

## 6. Target repository layout

The final repository MUST have the following logical layout. Files marked
"existing" are modified in place. Files marked "new" must be created.

~~~text
.
├── .env.example                              new
├── .gitignore                                new
├── .python-version                           new
├── .github/
│   └── workflows/
│       └── ci.yml                            new
├── README.md                                 existing, replace empty content
├── Dockerfile                                existing, secondary artifact
├── docker-compose.yml                        existing, secondary artifact
├── pyproject.toml                            existing
├── uv.lock                                   new, generated by uv
├── requirements/
│   └── vllm.txt                              new
├── docs/
│   ├── RESEARCH_TO_ARXIV_DESIGN.md           this file
│   ├── RESEARCH_PROPOSAL.md                  new
│   ├── EXPERIMENT_PROTOCOL.md                new
│   ├── EXPERIMENT_LOG.md                     new
│   └── RESULT_CLAIMS.md                      new
├── gateway/
│   ├── api/
│   │   └── routes.py                         existing
│   ├── backends/
│   │   ├── base.py                           existing
│   │   ├── factory.py                        new
│   │   ├── mock.py                           existing
│   │   └── vllm.py                           existing placeholder, implement
│   ├── clients/
│   │   └── backend_http.py                   existing placeholder, implement
│   ├── core/
│   │   ├── batcher.py                        existing, rewrite surgically
│   │   ├── clock.py                          new
│   │   ├── models.py                         existing
│   │   ├── service.py                        new
│   │   └── policies/
│   │       ├── __init__.py                   new
│   │       ├── base.py                       new
│   │       ├── fixed.py                      new
│   │       └── adaptive.py                   new
│   ├── observability/
│   │   ├── events.py                         new
│   │   ├── logging.py                        existing placeholder, implement
│   │   └── metrics.py                        existing placeholder, implement
│   ├── config.py                             existing
│   └── main.py                               existing
├── bench/
│   ├── __init__.py                           new if absent
│   ├── cli.py                                new
│   ├── config.py                             new
│   ├── arrivals.py                           new
│   ├── prompts.py                            new
│   ├── client.py                             new
│   ├── runner.py                             new
│   ├── schema.py                             new
│   ├── storage.py                            new
│   ├── gpu_monitor.py                        new
│   ├── summarize.py                          new
│   ├── plot.py                               new
│   └── data/
│       └── prompt_seeds.jsonl                new
├── configs/
│   ├── models/
│   │   ├── qwen2_5_1_5b.toml                new
│   │   └── qwen2_5_3b.toml                  new
│   ├── workloads/
│   │   ├── short_constant.toml               new
│   │   ├── mixed_poisson.toml                new
│   │   └── mixed_bursty.toml                 new
│   └── experiments/
│       ├── calibration.toml                  new
│       ├── fixed_window_pilot.toml           new
│       ├── fixed_window_sensitivity.toml     new
│       ├── adaptive_final.toml               new
│       └── qwen3b_validation.toml            new
├── scripts/
│   ├── setup-wsl.ps1                         new
│   ├── setup_gateway.sh                      new
│   ├── setup_vllm.sh                         new
│   ├── serve_vllm.sh                         new
│   ├── serve_gateway.sh                      new
│   ├── capture_system_info.sh                new
│   ├── run_calibration.sh                    new
│   ├── run_pilot.sh                          new
│   ├── run_final_experiments.sh              new
│   └── build_paper.sh                        new
├── tests/
│   ├── conftest.py                           new
│   ├── test_api.py                           existing
│   ├── test_backend_factory.py               new
│   ├── test_batcher.py                       existing
│   ├── test_batcher_shutdown.py              new
│   ├── test_fixed_policy.py                  new
│   ├── test_adaptive_policy.py               new
│   ├── test_mock_backend.py                  existing
│   ├── test_vllm_backend.py                  new
│   ├── test_arrivals.py                      new
│   ├── test_bench_config.py                  new
│   ├── test_bench_runner.py                  new
│   ├── test_storage.py                       new
│   └── test_summarize.py                     new
├── results/
│   ├── README.md                             new
│   ├── raw/                                  generated, gitignored
│   ├── summaries/                            generated, selected files tracked
│   ├── figures/                              generated, final files tracked
│   └── system/                               generated, selected files tracked
└── paper/
    ├── main.tex                              new
    ├── references.bib                        new
    ├── macros.tex                            new
    ├── sections/
    │   ├── 01_introduction.tex               new
    │   ├── 02_background.tex                 new
    │   ├── 03_methodology.tex                new
    │   ├── 04_design.tex                     new
    │   ├── 05_evaluation.tex                 new
    │   ├── 06_discussion.tex                 new
    │   └── 07_conclusion.tex                 new
    └── figures/                              generated or copied by script
~~~

Do not create empty speculative modules outside this layout.

## 7. File-by-file responsibilities

### 7.1 Root and environment files

#### .gitignore

Purpose: prevent generated Python, model, environment, raw result, and LaTeX
build files from entering Git.

It MUST ignore at least:

~~~gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.venv/
.env
*.egg-info/
dist/
build/
results/raw/
paper/*.aux
paper/*.bbl
paper/*.blg
paper/*.fdb_latexmk
paper/*.fls
paper/*.log
paper/*.out
paper/*.pdf
~~~

Final figure files under results/figures and paper/figures MUST NOT be ignored.

#### .env.example

Purpose: document gateway environment variables without storing secrets.

Required content:

~~~dotenv
ADIP_APP_HOST=127.0.0.1
ADIP_APP_PORT=8000
ADIP_BACKEND_KIND=vllm
ADIP_GATEWAY_MODE=pass_through
ADIP_VLLM_BASE_URL=http://127.0.0.1:8001
ADIP_VLLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct
ADIP_VLLM_API_KEY=
ADIP_VLLM_TIMEOUT_S=120
ADIP_BATCH_POLICY=fixed
ADIP_BATCH_MAX_SIZE=8
ADIP_BATCH_MAX_WAIT_MS=5
ADIP_QUEUE_MAX_SIZE=1024
ADIP_LOG_LEVEL=INFO
ADIP_RESEARCH_TELEMETRY=true
~~~

#### pyproject.toml

Purpose: define the gateway, benchmark, test, lint, and analysis dependencies.

Required changes:

- Set requires-python to >=3.12,<3.13 for the final experiment artifact.
- Move httpx into runtime dependencies because the vLLM adapter uses it.
- Add numpy, pandas, and matplotlib to a research dependency group.
- Keep pytest and pytest-asyncio in the dev group.
- Add ruff to the dev group.
- Configure setuptools to include gateway and bench packages.
- Configure pytest asyncio mode explicitly.

Expected relevant structure:

~~~toml
[project]
name = "adip"
version = "0.2.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.115,<1",
    "httpx>=0.27,<1",
    "pydantic>=2.8,<3",
    "pydantic-settings>=2.3,<3",
    "uvicorn>=0.30,<1",
]

[dependency-groups]
dev = [
    "pytest>=8.2,<9",
    "pytest-asyncio>=0.23,<1",
    "ruff>=0.8,<1",
]
research = [
    "matplotlib>=3.9,<4",
    "numpy>=2,<3",
    "pandas>=2.2,<3",
]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.setuptools.packages.find]
include = ["gateway*", "bench*"]
~~~

Agents MUST run uv lock rather than hand-writing uv.lock.

#### requirements/vllm.txt

Purpose: pin the isolated inference-server environment.

Required format:

~~~text
vllm==EXACT_TESTED_VERSION
~~~

Replace EXACT_TESTED_VERSION only after a successful RTX 3060 smoke test. Record
the chosen version in docs/EXPERIMENT_PROTOCOL.md and results/system/.

#### README.md

Purpose: public entry point for admissions reviewers and artifact users.

It MUST contain:

- One-paragraph project description.
- Research questions.
- Architecture diagram.
- Supported execution modes.
- WSL/Linux prerequisites.
- Exact quick-start commands.
- Exact benchmark commands.
- Link to the paper.
- Link to the results reproduction instructions.
- Scope and limitations.

README claims MUST be copied from docs/RESULT_CLAIMS.md, not improvised.

### 7.2 Gateway files

#### gateway/config.py

Purpose: validate all application configuration at startup.

Required settings:

- app_name: str
- app_host: str
- app_port: int
- backend_kind: Literal["mock", "vllm"]
- gateway_mode: Literal["pass_through", "batched"]
- batch_policy: Literal["fixed", "adaptive"]
- batch_max_size: positive int
- batch_max_wait_ms: nonnegative int
- queue_max_size: positive int
- mock backend latency fields
- vllm_base_url: str
- vllm_api_key: optional str
- vllm_model: str
- vllm_timeout_s: positive float
- adaptive_ewma_alpha: float in (0, 1]
- adaptive_low_load_threshold: nonnegative float
- research_telemetry: bool
- log_level: str

Configuration MUST fail at startup if a value is invalid. Do not silently clamp
invalid configuration.

#### gateway/core/clock.py

Purpose: make time-dependent scheduling deterministic in unit tests.

Required interface:

~~~python
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Return monotonic time in seconds."""


class SystemClock:
    def monotonic(self) -> float:
        """Return time.monotonic()."""
~~~

Tests will provide a FakeClock whose value can be advanced manually.

#### gateway/core/models.py

Purpose: define API models and internal request state.

Required public request:

~~~python
class InferenceRequest(BaseModel):
    input_text: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_tokens: int = Field(default=64, ge=1, le=256)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    deadline_ms: int | None = Field(default=None, ge=1)
~~~

deadline_ms is a soft end-to-end SLO measured from gateway receipt. It is not a
hard network timeout. A request may complete after its deadline and MUST then
be marked deadline_met=false. The gateway MUST use remaining deadline slack to
avoid unnecessary queue waiting.

Required public response:

~~~python
class InferenceResponse(BaseModel):
    request_id: str
    model: str
    output_text: str
    output_tokens: int | None
    batch_id: str | None
    batch_size: int
    queue_ms: float
    backend_ms: float
    total_ms: float
    deadline_met: bool | None
~~~

Required internal concepts:

- BatchKey: immutable tuple or dataclass containing model, max_tokens, and
  temperature.
- RequestMetadata: request ID, received time, enqueue time, optional deadline.
- PendingRequest: metadata, payload, and a correctly typed
  asyncio.Future[InferenceResponse].
- BackendOutput: output text and optional output-token count.
- BatchExecution: batch ID, batch key, dispatch time, and requests.

Requests MUST be batch-compatible only when their BatchKey values are equal.

#### gateway/backends/base.py

Purpose: define the backend contract.

Required interface:

~~~python
from collections.abc import Sequence
from typing import Protocol


class InferenceBackend(Protocol):
    async def infer_one(self, request: PendingRequest) -> BackendOutput:
        """Execute exactly one request."""

    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[BackendOutput]:
        """Execute compatible requests and preserve input order."""

    async def aclose(self) -> None:
        """Release connections and other backend resources."""
~~~

infer_batch MUST return exactly one output per input request and preserve order.
The batcher MUST reject any count mismatch.

#### gateway/clients/backend_http.py

Purpose: own shared HTTP transport behavior used by remote backends.

Required class:

~~~python
class BackendHttpClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        ...

    async def post_json(
        self,
        path: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        ...

    async def aclose(self) -> None:
        ...
~~~

post_json MUST:

- Send JSON using one reusable AsyncClient.
- Apply the bearer token only when configured.
- Raise on non-2xx status.
- Require a JSON object response.
- Never log the API key.

Tests MUST use httpx.MockTransport. Tests MUST NOT require a live vLLM server.

#### gateway/backends/vllm.py

Purpose: translate ADIP requests to vLLM's OpenAI-compatible completions API.

Required behavior:

- infer_one sends one prompt string.
- infer_batch sends a list of prompt strings.
- Both send one shared model, max_tokens, and temperature.
- Reject incompatible batches before issuing HTTP.
- Parse choices deterministically.
- For batched responses, map outputs back to prompt indices rather than relying
  on incidental response ordering if vLLM returns an index field.
- Return output token counts when usage data permits; otherwise return None.
- Close the shared BackendHttpClient.

Required payload shape:

~~~python
{
    "model": request.payload.model,
    "prompt": prompt_or_prompt_list,
    "max_tokens": request.payload.max_tokens,
    "temperature": request.payload.temperature,
}
~~~

Do not add chat-template handling in the gateway. Benchmark prompts must already
be suitable for the completions endpoint.

#### gateway/backends/factory.py

Purpose: construct exactly one configured backend.

Required function:

~~~python
def build_backend(settings: Settings) -> InferenceBackend:
    """Construct mock or vLLM backend from validated settings."""
~~~

It MUST have explicit branches for mock and vllm. It MUST raise ValueError for
an unsupported value even if static typing suggests the case is impossible.

#### gateway/core/policies/base.py

Purpose: separate batch-closing research policy from queue and backend code.

Required types:

~~~python
@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    now: float
    oldest_enqueued_at: float
    compatible_queue_size: int
    max_batch_size: int
    max_wait_s: float
    arrival_rate_per_s: float
    estimated_backend_s: float
    earliest_deadline_at: float | None


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    dispatch_now: bool
    wait_s: float
    reason: str


class BatchPolicy(Protocol):
    def decide(self, snapshot: QueueSnapshot) -> DispatchDecision:
        """Return a deterministic decision without sleeping or performing I/O."""
~~~

Requirements:

- decide MUST be pure and deterministic.
- wait_s MUST be zero when dispatch_now is true.
- wait_s MUST never be negative.
- reason MUST come from a documented finite set so it can be aggregated.

Required reasons:

- batch_full
- wait_window_elapsed
- deadline_slack_exhausted
- low_load_bypass
- estimated_fill
- configured_wait

#### gateway/core/policies/fixed.py

Purpose: reproduce the current maximum-size/maximum-wait policy correctly.

FixedWindowPolicy MUST:

- Dispatch immediately when queue size reaches max_batch_size.
- Dispatch immediately when oldest request age reaches max_wait_s.
- Dispatch before waiting would consume the earliest request's service slack.
- Otherwise return the remaining fixed wait.

The policy does not sleep and does not mutate state.

#### gateway/core/policies/adaptive.py

Purpose: implement the single modest research contribution.

Initial policy definition:

1. Calculate oldest_age.
2. Calculate remaining_window = max_wait_s - oldest_age.
3. Calculate expected_companions =
   arrival_rate_per_s * max(remaining_window, 0).
4. Calculate deadline_wait_budget, when a deadline exists, as:
   earliest_deadline_at - now - estimated_backend_s.
5. Dispatch for batch_full when the queue is full.
6. Dispatch for wait_window_elapsed when remaining_window <= 0.
7. Dispatch for deadline_slack_exhausted when deadline_wait_budget <= 0.
8. Dispatch for low_load_bypass when expected_companions <
   adaptive_low_load_threshold.
9. Otherwise calculate fill_eta =
   (max_batch_size - compatible_queue_size) / arrival_rate_per_s.
10. Wait for the minimum of remaining_window, fill_eta, and any positive
    deadline_wait_budget.

Division by zero MUST be handled explicitly. If arrival_rate_per_s <= 0, the
policy MUST select low_load_bypass.

The policy MUST remain under 100 lines excluding comments and docstrings unless
a design amendment explains why.

#### gateway/core/batcher.py

Purpose: manage compatible queues, wait for policy decisions, execute batches,
and resolve futures.

Required architecture:

- Maintain one queue state per BatchKey.
- Use one worker task per active BatchKey or one coordinator that treats keys
  independently. The implementation choice MUST be documented.
- Never place incompatible requests in one backend call.
- Generate one batch_id per dispatch.
- Record enqueue, dispatch, backend start, and backend completion times.
- Resolve every future exactly once.
- Propagate backend failures to every unresolved request in that batch.
- Remove cancelled requests before dispatch.
- On stop, reject queued requests and resolve in-flight bookkeeping.
- stop MUST be idempotent.
- start MUST be idempotent.
- infer before start or after stop MUST raise a clear RuntimeError.

The batcher MUST NOT contain fixed or adaptive policy formulas. It consumes the
BatchPolicy interface.

Important shutdown rule:

When stop cancels a worker that currently awaits backend inference, all
requests held in that local batch MUST receive BatcherStoppedError unless their
future is already complete. No future may remain pending after stop returns.

#### gateway/core/service.py

Purpose: choose pass-through or batched execution without putting mode branches
in the API route.

Required class:

~~~python
class InferenceService:
    def __init__(
        self,
        backend: InferenceBackend,
        batcher: DynamicBatcher,
        mode: Literal["pass_through", "batched"],
        clock: Clock,
    ) -> None:
        ...

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Execute through the configured mode and return normalized telemetry."""
~~~

Pass-through behavior:

- Generate request metadata.
- Call backend.infer_one directly.
- Report batch_size=1 and batch_id=None.
- Report queue_ms=0 or the measured near-zero service overhead consistently.

Batched behavior:

- Delegate to DynamicBatcher.infer.

#### gateway/api/routes.py

Purpose: HTTP translation only.

The route MUST:

- Read app.state.inference_service.
- Validate input using InferenceRequest.
- Call the service.
- Map QueueOverloadedError to 503.
- Map configured backend timeout to 504.
- Map unexpected backend errors to 502 without exposing secrets.
- Preserve FastAPI's 422 validation response.

The route MUST NOT implement batching, choose a backend, or compute metrics.

#### gateway/main.py

Purpose: compose configuration, backend, policy, batcher, service, and app
lifecycle.

Startup order:

1. Configure logging.
2. Build backend.
3. Build policy.
4. Build batcher.
5. Start batcher only when batched mode is selected.
6. Build service.
7. Store service in app.state.

Shutdown order:

1. Stop batcher.
2. Close backend.

Shutdown MUST attempt backend cleanup even if batcher shutdown raises.

#### gateway/observability/events.py

Purpose: define stable structured event schemas.

Required events:

- request_received
- request_enqueued
- policy_decision
- batch_dispatched
- batch_completed
- request_completed
- request_failed

Every event MUST include timestamp, event name, request_id or batch_id when
applicable, and experiment ID when provided through the X-ADIP-Experiment-ID
header.

#### gateway/observability/logging.py

Purpose: emit one JSON object per line.

It MUST:

- Use Python logging.
- Avoid logging prompt contents by default.
- Never log API keys.
- Include exception type and safe message on failure.
- Permit INFO for experiment records and DEBUG for local diagnosis.

#### gateway/observability/metrics.py

Purpose: hold lightweight in-process counters and latency observations needed
for policy inputs and diagnostics.

Do not add Prometheus in the first implementation. Required measurements:

- received requests
- completed requests
- failed requests
- rejected requests
- batches
- batch-size observations
- backend-latency EWMA
- arrival-rate EWMA per BatchKey

The research result MUST come from benchmark JSONL, not only in-process
counters.

### 7.3 Benchmark files

#### bench/config.py

Purpose: load and validate TOML experiment configuration.

Required function:

~~~python
def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load TOML, validate all fields, resolve paths, and return immutable config."""
~~~

Relative paths MUST resolve relative to the config file, not the current
working directory.

#### bench/schema.py

Purpose: define immutable benchmark records.

Required dataclasses:

- ModelConfig
- WorkloadConfig
- ArrivalConfig
- ExperimentConfig
- PlannedRequest
- RequestResult
- GpuSample
- RunManifest
- SummaryRecord

RequestResult MUST contain:

~~~python
@dataclass(frozen=True, slots=True)
class RequestResult:
    schema_version: int
    experiment_id: str
    run_id: str
    request_index: int
    policy: str
    model: str
    workload: str
    seed: int
    target_arrival_s: float
    actual_arrival_s: float
    completed_s: float | None
    input_tokens: int
    output_tokens: int | None
    batch_id: str | None
    batch_size: int | None
    queue_ms: float | None
    backend_ms: float | None
    latency_ms: float | None
    deadline_ms: int | None
    deadline_met: bool | None
    status_code: int | None
    error_type: str | None
~~~

schema_version MUST initially be 1. Any incompatible change requires
incrementing it.

#### bench/arrivals.py

Purpose: create arrival offsets independently of request execution.

Required functions:

~~~python
def constant_arrivals(rate_per_s: float, duration_s: float) -> list[float]:
    """Return deterministic equally spaced offsets beginning at zero."""


def poisson_arrivals(
    rate_per_s: float,
    duration_s: float,
    seed: int,
) -> list[float]:
    """Return offsets generated from exponential inter-arrival times."""


def bursty_arrivals(
    low_rate_per_s: float,
    high_rate_per_s: float,
    burst_probability: float,
    interval_s: float,
    duration_s: float,
    seed: int,
) -> list[float]:
    """Choose a rate per interval and generate Poisson arrivals within it."""
~~~

All returned offsets MUST satisfy 0 <= offset < duration_s and be sorted.
Identical inputs MUST return identical outputs.

#### bench/prompts.py

Purpose: generate deterministic, license-safe, length-controlled prompts.

Implementation rules:

- Store a small set of original project-authored seed passages in
  bench/data/prompt_seeds.jsonl.
- Do not copy copyrighted articles or proprietary conversations.
- Expand or combine seed passages deterministically.
- Tokenize with the exact tokenizer for the target model.
- Continue constructing text until it falls inside the requested token bucket.
- Persist generated prompt text, token count, seed ID, and model tokenizer
  revision in the run manifest.

Required function:

~~~python
def build_prompt_set(
    tokenizer: TokenCounter,
    buckets: tuple[PromptBucket, ...],
    prompts_per_bucket: int,
    seed: int,
) -> tuple[PreparedPrompt, ...]:
    """Return deterministic prompts whose token counts satisfy every bucket."""
~~~

If a prompt cannot be placed in its target bucket, raise an error. Do not
silently assign it to another bucket.

#### bench/client.py

Purpose: issue direct-vLLM or ADIP requests and normalize responses.

Required interface:

~~~python
class InferenceClient(Protocol):
    async def infer(self, request: PlannedRequest) -> ClientResult:
        """Send one request and return normalized client-side timing."""
~~~

Implement:

- DirectVllmClient for http://127.0.0.1:8001/v1/completions.
- AdipClient for http://127.0.0.1:8000/v1/infer.

Both clients MUST use the same model, prompt, max_tokens, and temperature.

#### bench/runner.py

Purpose: execute an open-loop schedule without coordinated omission.

Required behavior:

1. Load a fully resolved ExperimentConfig.
2. Generate all PlannedRequest objects before the run starts.
3. Choose a monotonic start time at least two seconds in the future.
4. Create one task per planned request.
5. Each task sleeps until its absolute target time.
6. Record actual send time immediately before the HTTP call.
7. Do not wait for prior requests to finish before sending later requests.
8. Record scheduling drift as actual_arrival_s - target_arrival_s.
9. Write each result as soon as it completes.
10. Return nonzero if more than the configured harness-error threshold fails.

Boilerplate scheduling shape:

~~~python
async def execute_planned_request(
    planned: PlannedRequest,
    start_time: float,
    clock: Clock,
    client: InferenceClient,
) -> RequestResult:
    target = start_time + planned.arrival_offset_s
    await asyncio.sleep(max(0.0, target - clock.monotonic()))
    actual = clock.monotonic()
    result = await client.infer(planned)
    return normalize_result(planned, actual, result)
~~~

A transport safety limit MAY exist, but it MUST NOT postpone an arrival
silently. If the harness cannot issue a planned request on time, record the
drift and mark a harness overload when drift exceeds the configured threshold.

#### bench/gpu_monitor.py

Purpose: sample the local GPU independently of request execution.

Use nvidia-smi with explicit query fields:

~~~text
timestamp,index,name,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu
~~~

Sampling interval: one second.

Each sample MUST contain experiment_id and run_id. If one sample fails, record
the error and continue. If nvidia-smi is unavailable for the entire run, mark
GPU telemetry unavailable in the manifest; do not fabricate zeros.

#### bench/storage.py

Purpose: perform append-safe JSONL writes and atomic manifest/summary writes.

Required functions:

~~~python
def append_jsonl(path: Path, record: Mapping[str, object]) -> None:
    """Append one compact JSON object followed by one newline."""


def write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    """Write to a sibling temporary file and atomically replace the target."""
~~~

Create parent directories explicitly. UTF-8 and newline="\n" are required.

#### bench/summarize.py

Purpose: transform raw request records into publication-ready aggregate data.

Required calculations:

- Offered request rate.
- Achieved request throughput.
- Achieved output-token throughput.
- Success and failure counts.
- p50, p95, and p99 latency using numpy.quantile.
- Mean and p95 queue latency.
- Mean backend latency.
- Mean batch size.
- SLO attainment percentage.
- Mean GPU utilization.
- Mean and maximum VRAM use.
- Mean power draw when available.
- Arrival scheduling-drift p95.

Warm-up records MUST be excluded. Failed requests MUST remain in counts and
must not contribute fake zero latencies.

#### bench/plot.py

Purpose: produce every paper figure from summary files.

Plot requirements:

- Use a noninteractive backend.
- Use colorblind-safe colors.
- Include units on every axis.
- Include 95% confidence intervals where repetitions exist.
- Export both PDF and PNG.
- Never embed a headline number manually.
- Make figure generation deterministic.

#### bench/cli.py

Purpose: one stable command-line interface.

Required commands:

~~~text
python -m bench.cli prepare-prompts --config PATH
python -m bench.cli run --config PATH
python -m bench.cli summarize --input PATH --output PATH
python -m bench.cli plot --summary PATH --output-dir PATH
python -m bench.cli validate-run --run-dir PATH
~~~

Each command MUST print the resolved configuration and output paths.

### 7.4 Configuration files

All research configurations MUST be committed TOML. Command-line overrides
SHOULD be limited to run ID and repetition number.

#### Model configuration example

configs/models/qwen2_5_1_5b.toml:

~~~toml
model_id = "Qwen/Qwen2.5-1.5B-Instruct"
served_name = "qwen2.5-1.5b"
revision = "PINNED_REVISION"
dtype = "float16"
max_model_len = 2048
gpu_memory_utilization = 0.85
max_num_seqs = 32
temperature = 0.0
max_tokens = 64
~~~

Replace PINNED_REVISION with the exact downloaded revision before final runs.

#### Workload configuration example

configs/workloads/mixed_poisson.toml:

~~~toml
name = "mixed-poisson"
arrival_kind = "poisson"
duration_s = 120
warmup_requests = 50
seed = 1729
rate_fraction_of_capacity = 0.75

[[prompt_buckets]]
name = "short"
minimum_tokens = 32
maximum_tokens = 128
weight = 0.50

[[prompt_buckets]]
name = "medium"
minimum_tokens = 129
maximum_tokens = 512
weight = 0.35

[[prompt_buckets]]
name = "long"
minimum_tokens = 513
maximum_tokens = 1024
weight = 0.15
~~~

Weights MUST sum to 1 within floating-point tolerance.

#### Experiment configuration requirements

Every experiment file MUST include:

- experiment name
- model config path
- workload config path
- target endpoint mode
- ADIP gateway mode
- policy
- max batch size
- max wait milliseconds
- repetition seeds
- cooldown seconds
- output directory
- SLO derivation rule
- expected server health URL

### 7.5 Script responsibilities

Every shell script MUST use:

~~~bash
#!/usr/bin/env bash
set -euo pipefail
~~~

Scripts MUST resolve the repository root from their own location. They MUST NOT
assume the caller's current directory.

#### scripts/setup_gateway.sh

- Install the pinned Python version through uv when needed.
- Create the repository .venv.
- Run uv sync with dev and research groups.
- Run the complete test suite.

Expected final line:

~~~text
Gateway environment ready.
~~~

#### scripts/setup_vllm.sh

- Create ~/venvs/adip-vllm.
- Install the exact requirements/vllm.txt.
- Print installed vLLM, PyTorch, and CUDA versions.
- Run python -m vllm.collect_env and save the output under results/system/.

#### scripts/serve_vllm.sh

- Read one model TOML file.
- Start vLLM on 127.0.0.1:8001.
- Pass the exact model revision and server settings.
- Write startup logs to a run-specific path.
- Wait for the health endpoint before returning success.

The script MUST NOT use latest model revisions implicitly in final runs.

#### scripts/serve_gateway.sh

- Read mode and policy from environment or explicit arguments.
- Start ADIP on 127.0.0.1:8000.
- Write logs to a run-specific path.
- Wait for GET /health before returning success.

#### scripts/capture_system_info.sh

Capture:

- date in UTC
- Git commit and dirty status
- OS and kernel
- CPU summary
- total RAM
- nvidia-smi full output
- GPU query output
- Python and uv versions
- vLLM version
- PyTorch version
- installed package list
- model configuration

Never capture environment-variable values that may contain secrets.

#### Experiment scripts

run_calibration.sh, run_pilot.sh, and run_final_experiments.sh MUST:

- Refuse to run from a dirty Git worktree unless ALLOW_DIRTY=1 is explicitly
  supplied.
- Create a unique run directory.
- Capture the manifest before sending load.
- Verify both server health endpoints.
- Run configurations in a deterministic order for pilots.
- Randomize policy order for final repetitions using a recorded seed.
- Run a cooldown between configurations.
- Validate every completed run directory.
- Stop on corrupt output, but retain already written evidence.

### 7.6 Documentation files

#### docs/RESEARCH_PROPOSAL.md

Purpose: freeze the study design before final experiments.

Required sections:

- Problem.
- Research questions.
- Hypotheses.
- Independent variables.
- Dependent variables.
- Controlled variables.
- Baselines.
- Exclusion criteria.
- Analysis method.
- Threats to validity.
- Planned claims.

This file MUST be committed before Phase 6 final experiments.

#### docs/EXPERIMENT_PROTOCOL.md

Purpose: exact operator instructions.

It MUST list commands from booting WSL through producing figures, including
which terminal runs vLLM, which runs ADIP, and which runs the benchmark.

#### docs/EXPERIMENT_LOG.md

Purpose: append-only human-readable record of experiment decisions and
anomalies.

Each entry MUST contain:

- UTC timestamp.
- Agent or operator.
- Git commit.
- Action.
- Observation.
- Decision.
- Whether any run was excluded and why.

Do not edit old entries to make later results look cleaner.

#### docs/RESULT_CLAIMS.md

Purpose: map every public claim to exact evidence.

Required table columns:

~~~text
Claim ID | Claim text | Figure/table | Configs | Raw run IDs | Status
~~~

No numerical claim may enter the abstract, README, or conclusion without an
entry in this table.

### 7.7 Results layout

Each run directory MUST look like:

~~~text
results/raw/EXPERIMENT_ID/RUN_ID/
├── manifest.json
├── requests.jsonl
├── gpu.jsonl
├── gateway.log
├── vllm.log
└── validation.json
~~~

manifest.json MUST include:

- schema version
- experiment ID
- run ID
- UTC start/end
- Git commit and dirty flag
- all resolved configuration
- random seed
- model ID and revision
- vLLM version
- hardware identity
- warm-up rule
- measurement duration
- process command lines with secrets removed

Raw result directories are immutable after validation. If a run is wrong,
record the exclusion and create a new run ID.

## 8. API contract

### 8.1 Health

Request:

~~~http
GET /health
~~~

Success:

~~~json
{"status":"ok","backend":"vllm","mode":"batched","policy":"fixed"}
~~~

Health MUST reflect configuration, but it does not need to issue an inference
request.

### 8.2 Inference

Request:

~~~http
POST /v1/infer
Content-Type: application/json
X-ADIP-Experiment-ID: optional-experiment-id
~~~

Body:

~~~json
{
  "input_text": "Explain dynamic batching in one paragraph.",
  "model": "qwen2.5-1.5b",
  "max_tokens": 64,
  "temperature": 0.0,
  "deadline_ms": 750
}
~~~

Success shape:

~~~json
{
  "request_id": "uuid",
  "model": "qwen2.5-1.5b",
  "output_text": "...",
  "output_tokens": 64,
  "batch_id": "uuid-or-null",
  "batch_size": 4,
  "queue_ms": 3.21,
  "backend_ms": 122.40,
  "total_ms": 125.91,
  "deadline_met": true
}
~~~

Error mapping:

- 422: invalid request.
- 503: ADIP queue capacity exceeded.
- 504: configured backend timeout.
- 502: backend protocol or HTTP failure.

Prompt contents MUST NOT appear in error logs by default.

## 9. Scheduling semantics

### 9.1 Compatibility

BatchKey MUST contain:

~~~text
model
max_tokens
temperature
~~~

Only equal BatchKey requests may share a backend request.

### 9.2 Deadline

deadline_ms is a soft SLO measured from gateway receipt to gateway response.

- It influences when a batch is dispatched.
- It does not cancel GPU execution after dispatch.
- It does not cause result deletion.
- deadline_met is computed after completion.
- A missing deadline produces deadline_met=null.

This definition MUST be identical in code, tests, README, and paper.

### 9.3 Queue capacity

queue_max_size is the maximum total number of accepted but unresolved requests
across all BatchKey queues. It is not a per-key limit.

Acceptance MUST be atomic. If the limit is reached, infer raises
QueueOverloadedError before creating unresolved background work.

### 9.4 Cancellation

If an HTTP client disconnects before dispatch:

- Cancel its future.
- Remove or skip the request.
- Do not count it in batch size.

If cancellation happens after backend dispatch:

- Do not attempt to cancel only part of an HTTP prompt batch.
- Let the backend call finish.
- Do not set a result on the cancelled future.
- Record request_failed with cancellation reason.

### 9.5 Shutdown

After DynamicBatcher.stop returns:

- No worker tasks remain.
- No pending future remains unresolved.
- No new request is accepted.
- A second stop call succeeds without changing state.

## 10. Testing specification

### 10.1 Test hierarchy

Unit tests:

- Pure policy decisions.
- Arrival generation.
- Configuration validation.
- Result summarization.
- Model compatibility.

Async component tests:

- Batcher grouping.
- Backend error propagation.
- Cancellation.
- Shutdown.
- Queue overload.

HTTP tests:

- API status codes and response shape.
- App lifespan.
- Pass-through versus batched mode.

Live smoke tests:

- Mark with pytest marker live_vllm.
- Exclude from default CI.
- Require explicit LIVE_VLLM_URL.

### 10.2 Fake time

Policy unit tests MUST use FakeClock. They MUST NOT depend on millisecond wall
clock sleeps.

Suggested fixture:

~~~python
class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds must be nonnegative")
        self.now += seconds
~~~

### 10.3 Required commands

Before any implementation commit:

~~~bash
uv run ruff check .
uv run pytest -q
~~~

Before final experiments:

~~~bash
uv run pytest -q
uv run pytest -q -m live_vllm
python -m bench.cli validate-run --run-dir PATH_TO_SMOKE_RUN
~~~

No agent may report a phase complete when a required command fails.

## 11. Experiment protocol

### 11.1 Controlled variables

Keep fixed within each model experiment:

- GPU and driver.
- vLLM version.
- Model ID and revision.
- dtype.
- max_model_len.
- gpu_memory_utilization.
- temperature.
- output token cap.
- prompt set.
- arrival schedule for paired policy comparisons.
- Windows power configuration.
- GPU-consuming background applications as far as practical.

### 11.2 Independent variables

- Endpoint mode: direct, pass-through, fixed, adaptive.
- Offered load.
- Arrival process.
- Prompt distribution.
- Fixed max wait.
- Fixed maximum batch size in sensitivity runs.

### 11.3 Primary model

Use Qwen/Qwen2.5-1.5B-Instruct in float16.

Starting settings:

~~~text
max_model_len=2048
gpu_memory_utilization=0.85
max_num_seqs=32
temperature=0.0
max_tokens=64
~~~

If this configuration fails, record the exact error. Reduce max_num_seqs first,
then gpu_memory_utilization only if initialization is the issue. Do not change
multiple variables at once.

### 11.4 Secondary model

Use Qwen/Qwen2.5-3B-Instruct in float16 for selected validation points.

Do not run the full matrix on the secondary model. Its purpose is to check
whether the main qualitative finding is unique to the 1.5B model.

### 11.5 Calibration

For each workload/model pair:

1. Start vLLM and wait until healthy.
2. Send 50 unmeasured warm-up requests.
3. Run direct vLLM at 0.5, 1, 2, 4, 8, and 16 requests/second.
4. Add higher or intermediate rates if needed.
5. Use 60-second pilot measurements.
6. Identify the highest rate where achieved throughput follows offered load and
   queue/latency does not grow without bound.
7. Save that value as measured_capacity_rps in a committed summary.

Final offered loads:

- 0.25 times measured capacity.
- 0.50 times measured capacity.
- 0.75 times measured capacity.
- 0.90 times measured capacity.
- 1.10 times measured capacity for overload characterization only.

### 11.6 SLO derivation

For each model/workload:

1. Run direct vLLM at 0.25 capacity.
2. Calculate p95 end-to-end latency.
3. Define strict SLO as 1.5 times this p95.
4. Define relaxed SLO as 2.0 times this p95.
5. Round only for display, not computation.
6. Commit the derived SLO file before final policy comparisons.

This rule MUST be applied equally to every policy.

### 11.7 Pilot matrix

Primary model only:

- Arrival processes: constant, Poisson, bursty.
- Workloads: short and mixed.
- Loads: 0.25, 0.75, 0.90 capacity.
- Modes: direct, pass-through, fixed.
- Fixed waits: 1, 5, 10, 20 ms.
- Max batch size: 8.
- Duration: 60 seconds.
- Repetitions: 1 for broad exploration, 3 for promising or surprising points.

Pilot results MUST NOT be mixed into final confidence intervals.

### 11.8 Final matrix

Primary model:

- Workloads: short-constant, mixed-Poisson, mixed-bursty.
- Loads: 0.25, 0.50, 0.75, 0.90 capacity.
- Policies: direct, pass-through, best fixed, adaptive.
- Duration: 120 seconds.
- Repetitions: 3.

Total: 3 x 4 x 4 x 3 = 144 runs.

Run order MUST be randomized within each repetition using a recorded seed.

### 11.9 Sensitivity matrix

Run on mixed-Poisson at 0.50 and 0.90 capacity:

- Waits: 1, 5, 10, 20 ms.
- Batch sizes: 4, 8, 16.
- Repetitions: 3.

If runtime is excessive, run the wait sweep first. The batch-size sweep MAY be
reduced to one load only, but the change must be recorded before looking at its
results.

### 11.10 Secondary-model validation

Use short-constant and mixed-bursty at 0.50 and 0.90 capacity:

- Direct.
- Pass-through.
- Best fixed.
- Adaptive.
- Three repetitions.

### 11.11 Thermal and background controls

- Record initial GPU temperature.
- Use a fixed cooldown, initially 30 seconds, between runs.
- If initial temperature differs by more than 10 degrees Celsius across runs,
  increase cooldown and record the decision.
- Close games, video rendering, and other GPU compute workloads.
- Ordinary desktop display usage may remain and must be acknowledged because
  the GPU runs in WDDM mode.
- Never delete a run due only to an unfavorable result.

### 11.12 Run exclusion

A run may be excluded only for:

- Server crash.
- Harness failure.
- Corrupt or incomplete result file.
- Accidental competing GPU workload documented with evidence.
- Configuration mismatch.

Every exclusion MUST appear in docs/EXPERIMENT_LOG.md with its run ID. Excluded
raw data MUST be retained.

## 12. Analysis specification

### 12.1 Unit of analysis

The request is the latency unit. The run is the replication unit.

Do not treat thousands of requests from one run as thousands of independent
experimental repetitions.

### 12.2 Confidence intervals

For each configuration:

- Compute the target metric separately for each run.
- Report the mean across runs.
- Compute a 95% confidence interval across run-level values.
- With only three repetitions, show each run point in plots and state that the
  interval estimate is limited.

### 12.3 Required comparisons

- Pass-through minus direct: proxy overhead.
- Fixed minus pass-through: external batching effect.
- Adaptive minus best fixed: adaptive-policy effect.
- Each policy under bursty minus constant: burst sensitivity.

Report absolute and relative differences.

### 12.4 Required figures

F1. Architecture and timing points.  
F2. Achieved throughput versus offered load.  
F3. p95 and p99 latency versus offered load.  
F4. Strict and relaxed SLO goodput versus offered load.  
F5. Throughput-latency Pareto frontier.  
F6. Batch-size distribution by policy and load.  
F7. Queue/backend latency decomposition.  
F8. Time-series response to burst transitions.  
F9. Fixed wait-window sensitivity.  
F10. GPU utilization and VRAM usage.  

Every figure caption MUST state the model, workload, repetition treatment, and
error-bar meaning.

### 12.5 Interpretation rules

- Do not call a difference significant without an appropriate statistical
  test or confidence-interval interpretation.
- Do not claim generality beyond one RTX 3060 and the tested models.
- Distinguish throughput from goodput.
- Distinguish offered load from achieved throughput.
- Distinguish gateway queue time from backend time.
- State when vLLM performs the dominant scheduling work.
- Negative or neutral adaptive results MUST remain visible.

## 13. Paper specification

### 13.1 Paper structure

paper/main.tex MUST include the section files in this order:

1. Introduction.
2. Background and related work.
3. Research questions and methodology.
4. ADIP design.
5. Evaluation.
6. Discussion and limitations.
7. Conclusion.

### 13.2 Section contents

#### Introduction

- Explain double batching.
- State why configuration is non-obvious.
- State the research questions.
- Summarize only verified headline results.
- List contributions.

#### Background

- Request-level and continuous batching.
- vLLM and PagedAttention.
- Orca iteration-level scheduling.
- Sarathi/Sarathi-Serve.
- SLO-aware serving work.
- Explain how ADIP differs: external, black-box, single-GPU study.

#### Methodology

- Hardware and software.
- Models.
- Workloads.
- Open-loop arrivals.
- Baselines.
- Metrics.
- SLO definition.
- Repetitions and uncertainty.

#### Design

- Gateway architecture.
- Compatibility keys.
- Fixed policy.
- Adaptive policy.
- Telemetry.
- Failure behavior.

#### Evaluation

Organize by research question, not by implementation component.

Each subsection MUST begin with the question and end with a one-sentence
finding.

#### Discussion

- Practical configuration advice.
- When not to use gateway batching.
- Interaction with vLLM continuous batching.
- Single-GPU limitations.
- WSL/WDDM limitations.
- Synthetic prompt limitations.
- External validity.

#### Conclusion

Restate only supported findings. Do not introduce a new result.

### 13.3 Abstract template

Do not fill numerical placeholders until docs/RESULT_CLAIMS.md verifies them.

~~~text
Large-language-model serving engines use continuous batching to improve GPU
utilization, yet API gateways may independently coalesce requests before they
reach the engine. We present ADIP, a lightweight gateway and measurement
artifact for studying this additional scheduling layer. On a single NVIDIA RTX
3060 using [MODELS], we evaluate direct vLLM, pass-through proxying, fixed
gateway batching, and an adaptive policy across [WORKLOADS]. We find that
[VERIFIED FINDING 1], while [VERIFIED FINDING 2]. The adaptive policy
[VERIFIED ADAPTIVE RESULT]. Our results provide reproducible evidence about
when gateway-level batching is useful and when it adds avoidable latency on
commodity hardware.
~~~

### 13.4 Bibliography

references.bib MUST include primary sources for at least:

- vLLM/PagedAttention.
- Orca.
- Sarathi and Sarathi-Serve.
- One SLO-aware serving paper.
- BurstGPT or another workload characterization source if used.
- Any statistical method not considered standard.

Agents MUST verify titles, authors, venues, years, and URLs from primary
sources. Do not invent BibTeX.

## 14. Execution phases and agent task cards

Each task below is atomic. An agent MUST complete its verification before the
next dependent task begins.

### ENV-001: Install and verify WSL2

Owner: human operator assisted by agent.  
Inputs: Windows administrator access.  
Changes: host configuration only.  
Output: Ubuntu 24.04 WSL2 on D:.  
Verify: wsl -l -v and nvidia-smi inside WSL.  
Stop if: reboot is pending or GPU is not visible.  

### ENV-002: Create Linux working copy

Inputs: successful ENV-001.  
Actions:

1. Install Git and uv prerequisites.
2. Clone the repository to ~/src/veloinference.
3. Confirm HEAD matches expected origin state.
4. Create codex/research-preprint.

Output: Linux-native working tree.  
Verify: git status --short is empty.  

### REP-001: Repository hygiene

Actions:

1. Add .gitignore.
2. Add .python-version.
3. Update pyproject.toml.
4. Generate uv.lock.
5. Replace README.
6. Add CI.
7. Remove generated tracked artifacts if any; do not remove user files.

Verify:

~~~bash
uv sync --group dev --group research
uv run ruff check .
uv run pytest -q
~~~

Output: reproducible gateway environment.

### DOC-001: Freeze research proposal

Create docs/RESEARCH_PROPOSAL.md using Section 7.6.

Verify:

- All RQs have metrics.
- All hypotheses have a falsifying outcome.
- Independent and controlled variables are separated.
- Planned exclusions are explicit.

Output: committed proposal before final experiments.

### CORE-001: Define models, clock, and backend interfaces

Modify only:

- gateway/core/models.py
- gateway/core/clock.py
- gateway/backends/base.py
- tests/conftest.py
- directly associated tests

Verify:

- mypy is not required unless added consistently.
- Ruff passes.
- Existing mock tests are updated and pass.
- BatchKey equality tests pass.

### BACKEND-001: Implement shared HTTP client

Implement gateway/clients/backend_http.py with MockTransport tests.

Verify:

- Header behavior.
- Timeout propagation.
- Non-JSON rejection.
- Non-2xx rejection.
- aclose idempotence.

### BACKEND-002: Implement vLLM adapter

Implement gateway/backends/vllm.py and tests/test_vllm_backend.py.

Verify with MockTransport first. Then run one live request after ENV-003.

### ENV-003: Install and smoke-test vLLM

Actions:

1. Pin a vLLM version.
2. Create isolated environment.
3. Start Qwen 1.5B.
4. Send one direct completion.
5. Save collect_env output.

Expected response:

- HTTP 200.
- At least one choice.
- Nonempty completion text or a valid zero-length completion only when the
  model immediately emits EOS; if EOS occurs repeatedly, adjust the smoke
  prompt, not the model settings.

### CORE-002: Implement fixed policy

Create policy base and fixed implementation.

Required test cases:

- Empty or invalid snapshots rejected.
- Full queue dispatches.
- Elapsed window dispatches.
- Positive remaining window waits.
- Deadline slack truncates wait.
- Decision reasons exactly match specification.

### CORE-003: Rewrite batcher for compatibility and shutdown

Implement the requirements in Section 7.2.

Verify:

- Concurrent compatible requests batch.
- Incompatible requests separate.
- Queue total capacity is enforced.
- Cancellation before and after dispatch.
- Backend exception reaches all requests.
- stop leaves no pending tasks/futures.

### CORE-004: Implement service, factory, routes, and lifecycle

Verify API modes with TestClient and fake backend.

Expected health response:

~~~json
{"status":"ok","backend":"mock","mode":"batched","policy":"fixed"}
~~~

### OBS-001: Add structured events and counters

Verify logs parse as one JSON object per line and contain no prompt text or API
key.

### BENCH-001: Define schemas and TOML loading

Verify valid configs load and every invalid boundary fails with a useful
message.

### BENCH-002: Implement arrivals and prompts

Verify determinism and token-bucket constraints.

### BENCH-003: Implement direct and ADIP clients

Verify normalized output using MockTransport.

### BENCH-004: Implement open-loop runner and storage

Verify with a local fake HTTP server or injected client:

- Requests launch at planned times.
- Slow prior responses do not postpone later target arrivals.
- Results are valid JSONL after interruption.
- Manifest writes atomically.

### BENCH-005: Implement GPU monitor

Verify one sample on the local machine and parser tests with stored sample
output.

### BENCH-006: Implement summarization and plots

Use a small checked-in synthetic fixture. Verify exact expected summary values
and existence of PDF/PNG outputs.

### EXP-001: Calibrate primary model

Follow Section 11.5. Do not implement the adaptive policy yet.

Output:

- Raw calibration runs.
- Calibration summary.
- Capacity selection rationale in EXPERIMENT_LOG.

### EXP-002: Run fixed-policy pilot

Follow Section 11.7.

Output:

- Pilot summaries and plots.
- Best fixed window selected by a predeclared Pareto rule.
- No final paper claim yet.

Pareto selection rule:

Choose the smallest fixed wait that is not dominated on both achieved
throughput and p95 latency across the 0.50 and 0.90 load points. If multiple
waits remain, choose the shortest wait. Record the calculation.

### CORE-005: Implement adaptive policy

Implement only the algorithm in Section 7.2. Do not tune on final-run data.

Allowed tuning data:

- Calibration.
- Fixed-policy pilot.
- Dedicated adaptive pilot runs.

Freeze adaptive parameters in RESEARCH_PROPOSAL before EXP-003.

### EXP-003: Run final primary-model matrix

Follow Section 11.8.

Stop and investigate if:

- Arrival drift p95 exceeds 10 ms at low or medium load.
- More than 1% of requests fail due to the harness.
- Server configuration differs between policies.
- GPU telemetry is missing from every run.

### EXP-004: Run sensitivity and secondary validation

Follow Sections 11.9 and 11.10.

### ANA-001: Produce final analysis

Actions:

1. Validate all runs.
2. Record exclusions.
3. Generate summaries.
4. Generate figures.
5. Fill docs/RESULT_CLAIMS.md.
6. Have a separate agent audit each headline number from raw run IDs.

### PAPER-001: Draft paper without headline numbers

Write background, methodology, design, and limitations while experiments run.
Leave numerical placeholders in abstract, introduction, and conclusion.

### PAPER-002: Insert verified results

Every inserted number MUST reference a Claim ID from RESULT_CLAIMS.

### PAPER-003: Reproduction audit

A fresh agent or person MUST:

1. Start from a clean clone.
2. Follow README.
3. Run tests.
4. Start vLLM and ADIP.
5. Reproduce one selected configuration.
6. Regenerate at least one principal figure.
7. Record discrepancies.

### RELEASE-001: Artifact and arXiv release

Actions:

1. Freeze code and configs.
2. Create a release tag.
3. Archive final raw results separately if too large for Git.
4. Build LaTeX from clean source.
5. Verify PDF fonts, references, figure readability, and metadata.
6. Upload arXiv source.
7. Inspect arXiv-generated PDF.
8. Fix only rendering/metadata issues unless a new version is warranted.

## 15. Agent workflow rules

Every coding agent MUST:

1. Read this entire document.
2. Read git status before editing.
3. Identify the exact task card being executed.
4. State assumptions and success criteria.
5. Read all files directly affected by the task.
6. Add or update tests with behavioral changes.
7. Change only files required by the task.
8. Run the task's verification commands.
9. Report files changed, tests run, and unresolved risks.
10. Update EXPERIMENT_LOG only for experiment or research-design decisions.

Agents MUST NOT:

- Delete or overwrite unrecognized user changes.
- Reformat unrelated files.
- Merge the feature branch wholesale.
- Change the research question silently.
- Tune using final test data.
- edit raw validated result files.
- Report tests as passing when dependencies prevented them from running.
- Add performance numbers from the mock backend to the paper.
- Claim GPU results without a saved manifest and raw records.
- Use cloud inference or remote GPUs.

## 16. Commit and review strategy

Use small commits aligned to task cards. Suggested commit subjects:

~~~text
chore: establish reproducible research environment
docs: freeze ADIP research proposal
feat: add typed backend contracts
feat: integrate vLLM completions backend
fix: make batching cancellation-safe
feat: add deterministic batching policies
feat: add open-loop benchmark runner
feat: record GPU and request telemetry
analysis: add reproducible summaries and figures
paper: add methodology and system design
paper: report verified evaluation results
~~~

Do not combine environment setup, scheduler behavior, benchmark methodology,
and paper results in one commit.

## 17. Phase completion gates

Gate A: Environment ready

- WSL2 on D:.
- GPU visible in WSL.
- Python 3.12.
- Tests pass.

Gate B: Real backend ready

- Direct Qwen 1.5B completion succeeds.
- Pass-through completion succeeds.
- Fixed batched completion succeeds.
- Live smoke tests pass.

Gate C: Benchmark valid

- Open-loop scheduling verified.
- Request JSONL validates.
- GPU samples validate.
- One run can be summarized and plotted.

Gate D: Study frozen

- Proposal committed.
- Calibration complete.
- SLOs derived.
- Best fixed policy selected by declared rule.
- Adaptive parameters frozen.

Gate E: Evidence complete

- 144 primary final runs complete or every omission documented.
- Sensitivity complete.
- Secondary validation complete.
- Exclusions logged.

Gate F: Paper defensible

- Claims mapped to evidence.
- Figures regenerate.
- Limitations explicit.
- Independent audit complete.

Gate G: Submission ready

- Clean-clone reproduction complete.
- Release tag exists.
- arXiv source compiles.
- Final PDF inspected.

No agent may skip a gate because later work appears to function.

## 18. Expected final outputs

The project is complete only when all of the following exist:

1. A public repository with clean setup and experiment instructions.
2. A tagged source release corresponding to the paper.
3. A tested vLLM-backed ADIP implementation.
4. Direct, pass-through, fixed, and adaptive execution modes.
5. Immutable raw request and GPU telemetry for final runs.
6. Machine-readable summaries.
7. Reproducible PDF and PNG figures.
8. A claim-to-evidence ledger.
9. An 8-10 page paper plus references and appendix.
10. A successfully rendered arXiv preprint.

The expected final paper must answer every research question, even when the
answer is that no meaningful benefit was observed.

## 19. Immediate execution sequence

When implementation begins, perform exactly this sequence:

1. ENV-001: install WSL2 on D: and reboot.
2. ENV-002: create the Linux-native working copy and research branch.
3. REP-001: establish Python 3.12, dependencies, lockfile, ignore rules, README,
   and CI.
4. DOC-001: write and commit the frozen proposal.
5. CORE-001 and BACKEND-001.
6. BACKEND-002 and ENV-003.
7. CORE-002, CORE-003, CORE-004, and OBS-001.
8. BENCH-001 through BENCH-006.
9. EXP-001 and EXP-002.
10. CORE-005.
11. Freeze adaptive parameters.
12. EXP-003 and EXP-004.
13. ANA-001.
14. PAPER-001 and PAPER-002.
15. PAPER-003.
16. RELEASE-001.

The next action after approval of this design is ENV-001. Application code
should not be modified before the supported Linux GPU environment is verified.
