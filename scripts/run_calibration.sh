#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${1:?usage: scripts/run_calibration.sh CONFIG_PATH}"

cd "${REPO_ROOT}"
exec .venv-vllm/bin/python -m bench.calibration --config "${CONFIG_PATH}"
