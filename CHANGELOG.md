# Changelog

## 1.1.0

- New: a standalone HTML report (`REPORT.html`) written next to `REPORT.md` by
  `run` and `report`: at-a-glance cards, headline table, per-task matrix with
  score bars and deltas, per-category table, sample stability, failure
  signatures, provenance and integrity. One file, inline CSS/JS, no network
  access, sortable columns. `--html PATH` writes it anywhere, `--no-html` skips
  it.
- New: **sample stability** — per task, whether independent samples of the same
  prompt agree, plus the mean within-task spread. Two samples that disagree by
  50 points cannot separate two close models, and the report now says so.
- New: **failure signatures** — failing assertions of the first attempt grouped
  by assertion name, in the markdown, HTML and JSON reports. A name failing in
  both samples is a systematic gap, not noise.
- New: `run --dry-run` prints the plan (tasks, caps, prompt size, call count,
  output ceiling, suite digest) and exits without contacting the endpoint.
- New: `report --strict` exits 1 when a run has missing, duplicated or failed
  records, for CI use.
- Fixed: `--top-p`, `--top-k` and `--seed` were parsed but never applied to the
  target; only `--temperature` reached the request.
- Fixed: a run that died before the first task (endpoint never ready, crash)
  left `run.json` claiming `status: "running"`; it is now `"failed"` with a
  `finished_at`.
- Fixed: `--resume` reused any record whose task/sample matched, so resuming
  into a directory written by another model or an edited suite silently mixed
  two benchmarks. It now refuses with an explanation.
- `write_reports()` returns a dict of paths (`markdown`, `json`, `html`) instead
  of a 2-tuple.

## 1.0.0

First public release.

- `modelbench` CLI: `list`, `validate`, `run`, `report`, `doctor`, `mock`,
  `self-test`, `init-suite`.
- Two bundled suites: `core-v2` (12 tasks, 296 hidden assertions) and
  `core-v1` (9 tasks, 108 assertions).
- OpenAI-compatible streaming client with TTFT, tokens/s, reasoning capture and
  `finish_reason` accounting. Standard library only.
- Crash-safe run records: `results.jsonl` plus every raw answer, extracted
  solution and grader output on disk.
- One automatic repair turn using only failing assertion messages;
  `final = max(first, repair)`.
- One automatic retry when an answer is cut by the token cap.
- Report generator: headline metrics, per-task and per-category tables,
  pairwise deltas, provenance (served id, suite digest), integrity checks.
- Mock model server and `self-test` for running the whole pipeline without a
  GPU or an API key.
- TOML configuration with `${VAR}` expansion, per-target sampling, optional
  server start/stop commands.
