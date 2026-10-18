# Changelog

## 1.3.0

- `modelbench inspect RUN` triages a finished run: every record that lost points,
  worst first, with its first failing assertion. `--task`/`--sample` shows one
  record in full — failing assertions, what the model actually wrote, and a
  unified diff against the task's reference solution. `--context`, `--full`,
  `--json`, `--suite`.
- Comparisons are noise-aware. `pairwise()` measures how far each task moved
  between its own samples; if the mean delta is inside that spread the report
  says "the gap is inside the noise" instead of naming a winner, and marks
  individual coin-flip tasks with `≈`. Console output ends with
  "within noise" or "beyond noise".
- 429/503 responses now honour `Retry-After` (capped at 120 s) instead of
  sleeping through the fixed 1-2-4-8 backoff. HTTP-date values and nonsense
  numbers are ignored rather than trusted.
- Grader crashes are labelled as such: a record whose grader never reached
  `RESULT` shows "the grader never reached a RESULT line" rather than passing
  a traceback off as a failing assertion.
- README: "Why did it fail?" section; 66 -> 74 tests.

## 1.2.0

- Sampling is pinned by default: `seed = 42`, and sample *n* of a task is sent
  with `seed + n - 1`. Previously an unset seed meant every sample inherited
  whatever the backend did, and two samples of one task were not guaranteed to
  be independent draws — a run could look stable because it was one sample
  counted twice.
- `run --no-seed` deliberately sends no seed, for measuring an endpoint's own
  drift. The run header and the report both say `seed not pinned`.
- Records now carry the seed actually used (`"seed": 43`), and `run.json`
  keeps the base seed, so a record can be reproduced on its own.
- Reports show sampling in Provenance (temperature, seed, `+1/sample`), flag
  `not pinned` seeds, and put a warning above the fold when two compared runs
  were sampled differently, naming the fields that differ.
- README: new "Seeds, pins and drift" section on why this matters and what a
  publishable comparison protocol looks like.

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
