# ADIP Experiment Protocol

Status: operator protocol; not yet executed  
Execution host: local Windows machine with WSL2 and RTX 3060  
Storage: C: drive  

This document is the step-by-step procedure for running experiments. An agent
must follow it literally and record deviations in docs/EXPERIMENT_LOG.md.

## 1. Preconditions

Before running any experiment:

- WSL2 is installed.
- Ubuntu 24.04 is version 2.
- WSL-side nvidia-smi sees the RTX 3060.
- The repository is in the WSL filesystem.
- The working tree is clean.
- A current commit hash is recorded.
- At least 20 GB is available to the WSL distribution.
- No other GPU compute workload is intentionally running.

Do not run final experiments from the Windows-mounted repository path. Use the
Linux repository inside the WSL filesystem.

## 2. Windows host setup

Run PowerShell as Administrator:

~~~powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
~~~

Reboot Windows.

After reboot:

~~~powershell
wsl.exe --update --web-download
wsl.exe --help
~~~

If the help output supports location installation, run:

~~~powershell
wsl.exe --install --no-launch --distribution Ubuntu-24.04 --location C:\WSL\Ubuntu-24.04
~~~

If location installation is not supported, do not silently use an unknown
location. Use the WSL export/import process approved by the operator and
record the exact storage path.

Verify:

~~~powershell
wsl.exe -l -v
wsl.exe -d Ubuntu-24.04 -- nvidia-smi
~~~

Expected:

- Ubuntu-24.04 appears.
- VERSION is 2.
- nvidia-smi reports the RTX 3060.

## 3. Linux environment setup

Open Ubuntu:

~~~powershell
wsl.exe -d Ubuntu-24.04
~~~

Inside Ubuntu:

~~~bash
sudo apt-get update
sudo apt-get install -y build-essential curl git
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv python install 3.12
mkdir -p "$HOME/src"
~~~

Copy the current Windows working tree into the Linux filesystem only if it does
not already exist:

~~~bash
if [ ! -d "$HOME/src/veloinference/.git" ]; then
    mkdir -p "$HOME/src/veloinference"
    cp -a /mnt/c/Users/Wasiq/Desktop/veloinference/. "$HOME/src/veloinference/"
fi
cd "$HOME/src/veloinference"
~~~

The Linux copy becomes the experiment execution copy. Make sure its commit
contains the latest Windows-side commits before proceeding.

Run:

~~~bash
uv sync --all-groups
uv lock
uv run ruff check .
uv run pytest -q
~~~

Expected:

- uv.lock is created.
- Lint passes.
- All async tests run through pytest-asyncio.
- No unknown asyncio configuration warning appears.

## 4. Gateway environment setup

Inside the Linux repository:

~~~bash
cp .env.example .env
mkdir -p results/raw results/summaries results/figures results/system
./scripts/capture_system_info.sh
~~~

Do not put secrets in .env or commit it.

## 5. vLLM environment setup

Create the isolated environment:

~~~bash
uv venv "$HOME/venvs/adip-vllm" --python 3.12
source "$HOME/venvs/adip-vllm/bin/activate"
python -m pip install --upgrade pip
~~~

Install vLLM only after selecting a version that supports the GPU and Python
environment. The exact version must be written to requirements/vllm.txt:

~~~text
vllm==EXACT_TESTED_VERSION
~~~

Then install:

~~~bash
python -m pip install -r requirements/vllm.txt
python -m vllm.collect_env | tee results/system/vllm_collect_env.txt
~~~

The vLLM version is not considered pinned until the collect_env output and
package version are saved.

## 6. Model download and server smoke test

Use Qwen/Qwen2.5-1.5B-Instruct first.

Set model cache inside WSL:

~~~bash
export HF_HOME="$HOME/.cache/huggingface"
mkdir -p "$HF_HOME"
~~~

Start vLLM on port 8001 with the committed model configuration. The exact
server command must be saved in the run manifest.

Verify:

~~~bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/v1/models
~~~

Send one completion request and save the response:

~~~bash
curl -s http://127.0.0.1:8001/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-1.5b","prompt":"Explain dynamic batching briefly.","max_tokens":16,"temperature":0.0}'
~~~

ENV-003 is complete only if this returns HTTP 200 and a parseable choices list.

## 7. ADIP smoke test

In a second WSL terminal:

~~~bash
cd "$HOME/src/veloinference"
source .venv/bin/activate
export ADIP_BACKEND_KIND=vllm
export ADIP_GATEWAY_MODE=pass_through
export ADIP_VLLM_BASE_URL=http://127.0.0.1:8001
./scripts/serve_gateway.sh
~~~

In a third terminal:

~~~bash
curl http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/v1/infer \
  -H "Content-Type: application/json" \
  -d '{"input_text":"Explain dynamic batching briefly.","model":"qwen2.5-1.5b","max_tokens":16,"temperature":0.0}'
~~~

Repeat with ADIP_GATEWAY_MODE=batched after pass-through succeeds.

## 8. Calibration

Run:

~~~bash
./scripts/run_calibration.sh configs/experiments/calibration.toml
~~~

The script must:

- Warm up the server.
- Test increasing direct request rates.
- Record all requests and GPU samples.
- Produce measured_capacity_rps.
- Stop when the server becomes unstable or queue growth is unbounded.

Do not choose final rates by intuition. Use measured capacity.

## 9. Pilot

Run:

~~~bash
./scripts/run_pilot.sh configs/experiments/fixed_window_pilot.toml
~~~

The pilot evaluates fixed waits of 1, 5, 10, and 20 milliseconds. Select the
shortest nondominated fixed policy using the rule in the research proposal.

Record the decision before implementing or evaluating the adaptive policy.

## 10. Final experiments

Before final runs:

- Freeze adaptive policy parameters.
- Commit the proposal and configuration changes.
- Capture system information.
- Verify the working tree is clean.
- Verify both services.

Run:

~~~bash
./scripts/run_final_experiments.sh configs/experiments/adaptive_final.toml
~~~

Then run validation:

~~~bash
./scripts/run_final_experiments.sh configs/experiments/qwen3b_validation.toml
~~~

The script must create one immutable directory per run.

## 11. Summarization and plots

For each experiment:

~~~bash
python -m bench.cli validate-run --run-dir results/raw/EXPERIMENT_ID/RUN_ID
python -m bench.cli summarize --input results/raw/EXPERIMENT_ID --output results/summaries/EXPERIMENT_ID.json
python -m bench.cli plot --summary results/summaries/EXPERIMENT_ID.json --output-dir results/figures/EXPERIMENT_ID
~~~

Do not edit summaries or figures by hand. Fix the analysis code and regenerate.

## 12. Paper build

After claims are recorded:

~~~bash
./scripts/build_paper.sh
~~~

The script must fail on LaTeX errors and output a PDF under paper/.

## 13. Clean-clone reproduction

Use a separate clean checkout inside WSL. Repeat:

- Environment setup.
- Dependency installation.
- Tests.
- One live smoke test.
- One selected experiment.
- One principal figure.

Record the reproduction outcome in docs/EXPERIMENT_LOG.md.
