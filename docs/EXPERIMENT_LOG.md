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

## 2026-09-13 — EXP-002 fixed-window pilot

- Task ID: EXP-002.
- Implementation commits: `9f5d9f2`, `4e3894c`, `e0cb26c`, `368da2b`,
  `974ec10`.
- Runtime: WSL `Ubuntu`, Python 3.12, vLLM 0.29.0, Qwen/Qwen2.5-1.5B-Instruct
  revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, RTX 3060 12 GB.
- Controlled workload: tokenizer-backed short prompts, 30 seconds measured
  traffic, 10 warm-up requests per condition, 64 maximum output tokens,
  temperature 0, constant arrivals, fixed maximum batch size 8.
- Conditions: gateway waits 1, 5, 10, and 20 ms; offered rates 0.5, 1.0,
  and 2.0 requests/second, plus a separate 1.8 requests/second extension for
  the protocol's 0.90 point because EXP-001's valid ceiling was 2.0 rps.

### Failed attempt and exclusion

- The first pilot implementation produced 12 complete-looking runs, but every
  batch had size 1 and queue latency grew sharply at 1 and 2 rps.
- A focused slow-backend regression test reproduced the cause: after a slow
  backend call, the batcher selected one aged request before draining requests
  already waiting in the ingress queue.
- Those artifacts are preserved at
  `/home/kennarr/src/veloinference/results/raw/exp002-fixed-window-pilot-attempt-singletons-20260913`
  and are excluded from all pilot analysis.
- Commit `368da2b` drains already queued work before fixed-policy selection;
  the full batcher test file then passed 5/5.

### Corrected observations

- The corrected pilot produced 12 complete conditions, all with zero request
  failures and `git_dirty:false` manifests. The 1.8 rps extension produced 4
  additional complete conditions, also with zero failures.
- At the 0.50 point, p95 latency in milliseconds for waits 1/5/10/20 was
  approximately 1919.9 / 1929.8 / 1963.7 / 1791.5.
- At the 0.90 point (1.8 rps), p95 latency for waits 1/5/10/20 was
  approximately 3786.8 / 2814.4 / 3300.9 / 3392.2.
- Mean batch sizes at the 0.90 point for waits 1/5/10/20 were approximately
  3.19 / 2.59 / 2.93 / 2.96, confirming that the corrected gateway formed
  multi-request batches under load.
- All 16 corrected conditions achieved their offered request rate with 100%
  successful requests. These are exploratory pilot observations, not final
  repeated headline claims.

### Fixed-policy selection

- Selection rule: compare throughput and p95 latency at the 0.50 and 0.90
  points; remove waits dominated on both metrics; choose the shortest wait
  among the remaining waits.
- Because every corrected condition achieved its offered rate, throughput did
  not distinguish the waits. Wait 10 ms was dominated by wait 5 ms on p95 at
  both selection points. Waits 1, 5, and 20 ms remained nondominated because
  each traded lower p95 at one point against another wait's lower p95 at the
  other point.
- Decision: select the 1 ms fixed wait for EXP-003, because it is the shortest
  nondominated wait. This decision was made from pilot data before adaptive
  final experiments and must not be changed based on final-run results.
- Corrected raw artifacts:
  `/home/kennarr/src/veloinference/results/raw/exp002-fixed-window-pilot`
  and
  `/home/kennarr/src/veloinference/results/raw/exp002-fixed-window-pilot-90pct`.
- Generated aggregate summaries are under
  `/home/kennarr/src/veloinference/results/summaries/generated/` and remain
  ignored generated files. The raw directories and generated summaries are
  intentionally excluded from Git; the exact commands, configs, run IDs, and
  observed values are recorded here for the local reproduction audit.
- Decision status: exploratory pilot complete. Next action: freeze the
  adaptive-policy parameters without using EXP-003 final-run data.
