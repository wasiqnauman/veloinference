# ADIP

Async Dynamic Inference Proxy.

This repository contains a model-agnostic inference gateway with dynamic request batching, backend adapters, benchmarking, and observability.

## Development

- Python target: `3.14`
- Package manager: `uv`

```bash
uv sync
uv run python -m gateway.main
```

## vLLM Integration

The gateway can now be wired to either the synthetic `mock` backend or a real vLLM server. The intended first production-like setup is to keep vLLM as a separate process and let ADIP talk to its OpenAI-compatible HTTP API. That keeps the gateway simple, mirrors how teams usually deploy vLLM, and makes it easy to compare `direct` versus `batched` paths against the same model server.

Recommended environment variables:

```bash
export ADIP_BACKEND_KIND=vllm
export ADIP_VLLM_BASE_URL=http://127.0.0.1:8001
export ADIP_VLLM_MODEL=meta-llama/Llama-3.2-1B-Instruct
export ADIP_VLLM_MAX_TOKENS=64
export ADIP_VLLM_TEMPERATURE=0.0
```

Example vLLM server launch:

```bash
vllm serve meta-llama/Llama-3.2-1B-Instruct --port 8001
```

Then start the gateway:

```bash
uv run python -m gateway.main
```

The current adapter sends single requests and explicit prompt batches to vLLM's `/v1/completions` endpoint. That is enough to begin end-to-end testing of ADIP's batching behavior before adding richer generation controls, streaming, or token accounting.

Current limitation: the first vLLM path assumes one model per batch. If you want true multi-model serving, the scheduler should partition queues by resolved model ID before dispatch.

## Real Benchmark Plan

The current `bench/` harness is a good skeleton, but the existing workload is still synthetic. For credible vLLM results, we should treat this as a controlled benchmark and record the workload design along with the numbers.

### 1. Choose Two Models On Purpose

Use one model for smoke tests and one for realistic throughput tests:

- `meta-llama/Llama-3.2-1B-Instruct` for early bring-up. It is a 1.23B-parameter, decoder-only autoregressive transformer with GQA and a 128k context window, so it is small enough to make local integration work cheap and fast.
- `meta-llama/Llama-3.1-8B-Instruct` for more realistic batching measurements. It is an 8B-parameter decoder-only autoregressive transformer with GQA and a 128k context window, which makes it a better proxy for the latency and memory pressure seen in real serving stacks.

Keep the benchmark report explicit about the exact model ID, precision, tensor parallelism, GPU type, and vLLM flags. Throughput numbers without that metadata are hard to compare.

### 2. Replace The Toy Prompt Set

The current benchmark loops over four short strings. That is fine for a demo, but it does not exercise tokenizer cost, KV-cache growth, or long-tail latency. Move to a token-aware prompt corpus and publish the distribution used for the run.

Recommended baseline prompt-length distribution:

- `50%` short prompts: `32-128` input tokens
- `30%` medium prompts: `128-512` input tokens
- `15%` long prompts: `512-1024` input tokens
- `5%` extra-long prompts: `1024-2048` input tokens

Keep output length fixed at first, for example `64` generated tokens, so the first round isolates prompt-side batching behavior. After that, add a second experiment with mixed output caps such as `32`, `64`, and `128` tokens.

### 3. Measure Tokens, Not Just Strings

Prompt length should be reported in model tokens, not characters or words. Use the tokenizer associated with the exact deployed model and store:

- prompt token count
- requested output token cap
- total tokens per request
- prompt length bucket used in analysis

This matters because batching behavior is driven by token count and sequence shape, not by string length. A four-line English prompt and a four-line code prompt can tokenize very differently.

### 4. Add A Warm-Up Phase

Do not trust the first benchmark run. vLLM and the model stack often pay one-time costs early: CUDA graph capture, kernel autotuning, memory allocation, cache initialization, and model server startup effects.

Recommended warm-up procedure:

- start vLLM and wait for the model to load fully
- send `100-200` warm-up requests before collecting any measurements
- use the same prompt-length distribution as the real workload
- discard all warm-up samples from the final report

### 5. Report Variance Across Runs

Single-run results are too fragile. Run each configuration at least `5` times and report:

- mean throughput
- mean latency, `p95`, and `p99`
- standard deviation or coefficient of variation
- `95%` confidence intervals or min/max error bars

If the variance is high, keep the raw per-run data. That usually means one of three things is happening: the GPU is being shared, the workload mix is too bursty, or the batching window is interacting badly with request arrival patterns.

### 6. Sweep The Batching Window

Right now the gateway uses a fixed `batch_max_wait_ms` window. We should not hard-code that value based on intuition. Sweep it.

Recommended first sweep:

- wait window: `1`, `2`, `5`, `10`, `20`, `40` ms
- max batch size: `4`, `8`, `16`
- client concurrency: `8`, `16`, `32`, `64`, `128`

Choose the batching window from the Pareto frontier rather than from the single highest throughput point. In practice, the best setting is usually the smallest wait window that captures most of the throughput gain without creating an unacceptable `p95` or `p99` regression.

### 7. What To Implement Next In This Repo

To make the above practical, the next code changes should be:

1. Extend `bench/scenarios.py` so workloads can be loaded from a JSONL or CSV prompt corpus instead of four hard-coded strings.
2. Add token counting to the benchmark output, ideally by recording `prompt_tokens` and `max_tokens` per request.
3. Add repeated-run support to `bench/load_test.py` so we can emit raw per-run summaries and error bars.
4. Add a benchmark metadata block to each result file with model ID, precision, GPU, vLLM version, and gateway batching settings.

## Benchmarking

Run a direct-versus-batched comparison:

```bash
uv run python -m bench.load_test --mode compare --requests 500 --concurrency 64 --workload mixed-prompts
```

Run a concurrency sweep and save the raw results:

```bash
uv run python -m bench.load_test --requests 500 --workload mixed-prompts --sweep 8,16,32,64 --output bench/results/mock_sweep.json
```

Render a recruiter-friendly report from saved results:

```bash
uv run python -m bench.report bench/results/mock_sweep.json
```

## Performance Story

ADIP improves model serving the same way a shuttle improves traffic flow. Instead of sending one rider per car, the gateway waits a few milliseconds, fills the seats, and sends several requests together. That lets the backend spend less time repeating the same fixed setup cost for each individual request.

In the current mock-backend benchmark at concurrency `64`, batching increased throughput from `~100 req/s` to `~320 req/s` while cutting average latency from about `1.26 s` to `0.37 s`. The gateway reached an average batch size of `~8`, which is why the system delivered more work with less waiting.
