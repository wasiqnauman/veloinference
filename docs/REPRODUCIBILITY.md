# Reproducing the final experiment

This guide covers the public, frozen experiment path. The final matrix compares
direct vLLM access with ADIP pass-through, fixed batching, and adaptive
batching.

## Requirements

- Linux or WSL2 with a CUDA-capable NVIDIA GPU
- Python 3.12
- `uv`
- enough VRAM for `Qwen/Qwen2.5-1.5B-Instruct` with the committed model settings

The published run used an RTX 3060 with 12 GB of VRAM. Different hardware or
software versions are valid replications, but they are not expected to match
the reported latency values exactly.

## Install

Create the CPU-safe project environment:

```bash
uv sync --all-groups
uv run ruff check .
uv run pytest -q
```

Keep the GPU runtime separate from the project lockfile:

```bash
uv venv --python 3.12 --seed .venv-vllm
uv pip install --python .venv-vllm/bin/python -r requirements/vllm.txt
```

## Start vLLM

```bash
.venv-vllm/bin/vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --host 127.0.0.1 \
  --port 8001 \
  --dtype half \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 8 \
  --enforce-eager \
  --served-model-name Qwen/Qwen2.5-1.5B-Instruct
```

Wait for `http://127.0.0.1:8001/health` to report healthy before starting the
matrix.

## Run the matrix

The committed configuration freezes the four modes, offered rates, repetition
seeds, workload, model revision, and harness-validity thresholds:

```bash
./scripts/run_final_experiments.sh configs/experiments/primary_final.toml
```

Each condition writes request records, a manifest, and a summary beneath
`results/raw/exp003-primary-final/`. Existing complete conditions are reused,
so an interrupted matrix can be resumed with the same command.

## Analyze

```bash
uv run --group research python -m bench.analyze_final \
  --input results/raw/exp003-primary-final \
  --summary results/summaries/generated/exp003-analysis.json \
  --figure-dir tmp/paper-figures \
  --table-dir tmp/paper-tables
```

The analyzer requires all 48 declared conditions, excludes runs that fail the
arrival-drift or request-error gates, and computes paired effects by repetition
seed. Compare a new summary with the committed artifact rather than expecting
bit-for-bit timing agreement across machines.

## Public artifact boundary

This public repository includes the implementation, frozen final configuration,
tests, analysis code, final machine-readable summary, and the published paper
PDF at `paper/main.pdf`. The LaTeX source, manuscript figures and tables, and raw
request-level and GPU-monitor traces remain in the private research archive.
Generated figures and tables from the command above go under `tmp/` and stay out
of the public source tree.
