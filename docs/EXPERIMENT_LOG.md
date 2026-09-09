# ADIP Experiment Log

This file is append-only. Do not rewrite earlier entries to improve the story.
Record anomalies, failed runs, exclusions, and design changes.

## 2026-09-09 — Baseline and environment status

- Task IDs: BASELINE-001, DESIGN-001, STORAGE-001, ENV-001.
- Commits: ac80fa2, 3f35f60.
- Observation: the repository is a phase-one mock inference gateway.
- Observation: the RTX 3060 is visible to Windows with 12 GB VRAM.
- Observation: C: has sufficient free space for the planned local setup.
- Observation: WSL is not installed.
- Observation: DISM commands from the Codex shell returned error 740 because
  Windows Administrator privileges were unavailable.
- Decision: do not install vLLM or begin GPU experiments until WSL2 and
  WSL-side nvidia-smi succeed.
- Exclusion: none.

## 2026-09-09 — Repository scaffolding

- Task ID: REP-001A.
- Commit: 9d952bf.
- Added Python 3.12 pin, CI, dependency groups, README, ignore rules, and
  environment templates.
- Verification: pyproject.toml parsed; five synchronous tests passed in the
  host Python 3.13 environment.
- Limitation: full lock/install/test verification is deferred to WSL because
  Python 3.12 and pytest-asyncio are not available in the host shell.
- Exclusion: none.

## Future entry format

~~~text
YYYY-MM-DD HH:MM UTC
Task ID:
Commit:
Command:
Observation:
Metric:
Decision:
Exclusion:
Next action:
~~~
