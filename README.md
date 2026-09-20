# ADIP

ADIP is an Async Dynamic Inference Proxy for studying request batching at an
inference gateway.

The research question is practical:

> When does batching requests in an external gateway improve throughput, and
> when does the added waiting hurt latency when the backend already performs
> continuous batching?

The project will compare direct vLLM serving, gateway pass-through, fixed
gateway batching, and a small adaptive batching policy on one local NVIDIA
RTX 3060 with 12 GB of VRAM. The final result will be an empirical systems
paper and reproducible benchmark artifact, not a claim that ADIP replaces
production inference engines.

## Project documents

- Research-to-arXiv design: docs/RESEARCH_TO_ARXIV_DESIGN.md
- Implementation progress tracker: docs/PROGRESS.md
- Paper understanding and faculty-defense manual:
  docs/PAPER_DEFENSE_MANUAL.md

The design document is normative. The progress tracker records what has
actually been completed and tells the next agent exactly where to continue.

## Repository status

The repository currently contains the phase-one mock gateway and the
research-to-arXiv design. The Linux GPU environment is still being prepared.
The next environment milestone is WSL2 with Ubuntu 24.04 and CUDA visibility.

## Target architecture

~~~text
Open-loop benchmark client
    |
    +--> direct mode:   vLLM on 127.0.0.1:8001
    |
    +--> gateway modes: ADIP on 127.0.0.1:8000
                              |
                              +--> vLLM on 127.0.0.1:8001
                                      |
                                      +--> local RTX 3060
~~~

## Development prerequisites

The supported vLLM path runs under Linux. On the current Windows machine, use
WSL2 with Ubuntu 24.04. Store the WSL distribution and project files on C:.
Do not run the Linux project from /mnt/c; keep the repository inside the WSL
filesystem.

After WSL2 and Ubuntu are available:

~~~bash
cd ~/src/veloinference
uv sync --all-groups
uv run ruff check .
uv run pytest -q
~~~

The gateway-only development environment uses Python 3.12. The vLLM server is
installed into a separate Python environment so its dependencies do not
pollute the gateway environment.

## Local service ports

- vLLM: http://127.0.0.1:8001
- ADIP: http://127.0.0.1:8000

## Mock gateway

The current mock service can be started with:

~~~bash
uv run python -m gateway.main
~~~

Then check:

~~~bash
curl http://127.0.0.1:8000/health
~~~

The mock backend is for development and unit tests. It must not be used for
headline research results.

## Research workflow

The eventual local workflow is:

1. Start the pinned vLLM server.
2. Start ADIP in direct pass-through or batched mode.
3. Run an open-loop benchmark from a committed TOML configuration.
4. Save immutable request-level and GPU-level JSONL records.
5. Generate summaries and figures from raw records.
6. Map every paper claim to run IDs in docs/RESULT_CLAIMS.md.

All final experiments must run on the local RTX 3060. Cloud endpoints and
remote GPUs are outside the project scope.
