# ENV-003: vLLM RTX 3060 smoke test

This document records the first successful live vLLM request for the ADIP
project. It is an environment validation record, not a research result.

## Scope and outcome

The smoke test uses the Linux-native checkout inside WSL and keeps vLLM out of
the CPU-safe project environment and `uv.lock`.

| Item | Observed value |
| --- | --- |
| Host GPU | NVIDIA GeForce RTX 3060, 12 GB |
| WSL distro | `Ubuntu`, WSL2, Ubuntu 26.04 LTS |
| Python | CPython 3.12.14 from uv |
| vLLM | 0.29.0 |
| PyTorch | 2.13.0+cu132; CUDA runtime reported by PyTorch: 13.2 |
| FlashInfer | 0.6.18 |
| CUDA compiler | `nvcc` 13.4.59 |
| CUDA runtime package | 13.4.49 |
| Build tool | ninja 1.13.2 |
| Model | `Qwen/Qwen2.5-1.5B-Instruct` |
| Server | `127.0.0.1:8001` |

The server loaded the model, completed JIT warmup, returned HTTP 200 for one
`/v1/completions` request, and reported 13 prompt tokens, 32 completion
tokens, and 45 total tokens. The server was then stopped with Ctrl+C.

## One-time setup

Run these commands inside WSL. The repository path is Linux-native so model
loading and FlashInfer compilation do not depend on `/mnt/c`.

```bash
cd /home/kennarr/src/veloinference
uv venv --python 3.12 --seed .venv-vllm
uv pip install --python .venv-vllm/bin/python -r requirements/vllm.txt
```

The runtime-only environment must verify the GPU before starting a server:

```bash
.venv-vllm/bin/python -c \
  "import torch; print(torch.__version__); print(torch.version.cuda); \
print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

Expected result includes:

```text
2.13.0+cu132
13.2
True
NVIDIA GeForce RTX 3060
```

## WSL CUDA path setup

The Python CUDA wheels place the toolkit under `site-packages/nvidia/cu13`
instead of the conventional `/usr/local/cuda` layout. FlashInfer expects the
conventional `lib64` and `stubs` paths, so create the following small,
recoverable symlink layout once:

```bash
cd /home/kennarr/src/veloinference/.venv-vllm/lib/python3.12/site-packages/nvidia/cu13
test -e lib64 || ln -s lib lib64
mkdir -p lib/stubs
test -e lib/stubs/libcuda.so || ln -s /usr/lib/wsl/lib/libcuda.so lib/stubs/libcuda.so
test -e lib/libcudart.so || ln -s libcudart.so.13 lib/libcudart.so
```

Before each supervised server run, use literal paths as follows. This avoids
PowerShell expanding Bash variables when a WSL command is launched from the
Windows checkout:

```bash
export CUDA_HOME=/home/kennarr/src/veloinference/.venv-vllm/lib/python3.12/site-packages/nvidia/cu13
export PATH=/home/kennarr/src/veloinference/.venv-vllm/bin:/home/kennarr/src/veloinference/.venv-vllm/lib/python3.12/site-packages/nvidia/cu13/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/home/kennarr/src/veloinference/.venv-vllm/lib/python3.12/site-packages/nvidia/cu13/lib:/usr/lib/wsl/lib:/usr/lib
export VLLM_WSL2_ENABLE_PIN_MEMORY=1
```

`VLLM_WSL2_ENABLE_PIN_MEMORY=1` is required on this WSL2 setup because the
default vLLM startup path reports `RuntimeError: UVA is not available`.

## Start the server

Start this command in a supervised terminal and leave it running until the
smoke request succeeds:

```bash
cd /home/kennarr/src/veloinference
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

Do not begin a benchmark when startup only reaches model loading. The required
startup evidence is:

```text
Starting vLLM server on http://127.0.0.1:8001
Application startup complete.
```

## Send exactly one direct completion

Use this request after the startup evidence appears:

```bash
.venv-vllm/bin/python -c "import json, urllib.request; payload={'model':'Qwen/Qwen2.5-1.5B-Instruct','prompt':'In one short sentence, explain why batching can improve GPU throughput.','max_tokens':32,'temperature':0.0}; request=urllib.request.Request('http://127.0.0.1:8001/v1/completions', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(request, timeout=60).read().decode())"
```

The response must be JSON with these fields:

- `model` equal to `Qwen/Qwen2.5-1.5B-Instruct`.
- `choices[0].text` containing non-empty generated text.
- `usage.prompt_tokens`, `usage.completion_tokens`, and `usage.total_tokens`.

The recorded run returned HTTP 200 and a non-empty completion with usage
`prompt_tokens=13`, `completion_tokens=32`, and `total_tokens=45`.

## Stop and verify cleanup

Stop the supervised server with Ctrl+C. A clean follow-up check should show no
vLLM process and no listener on port 8001:

```bash
ps -eo pid,cmd | grep -E "vllm serve|EngineCore" | grep -v grep || true
ss -ltn "sport = :8001" || true
```

The shutdown path may print a vLLM `EngineDeadError` after Ctrl+C while the
request has already completed. Treat the smoke test as successful only when
the request itself returned HTTP 200 and the server had first reported
`Application startup complete.`

## What this does and does not prove

This test proves that the pinned local WSL environment can load the selected
model and serve one direct completion on the RTX 3060. It does not prove that
the gateway, dynamic batcher, policies, or any research hypothesis works.
Those require the later service integration and controlled benchmark tasks.
