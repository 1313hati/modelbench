# Changelog

## 2.0.0

The release where the benchmark starts reporting its own uncertainty, its cost,
and the work it was always claiming to be able to score.

- **Every score carries a 95% confidence interval.** `stats.py` bootstraps over
  **tasks**, the unit the score weights equally, with a fixed seed, so a CI
  quoted in a pull request still matches the CI regenerated from disk. The
  headline, markdown, HTML card and JSON all print it. A single-sample run gets
  no interval at all — `(v, v)` would claim certainty the suite does not have.
- **A comparison can now conclude "not established".** `pairwise()` gains a
  bootstrap interval on the mean per-task delta and an exact two-sided sign
  test. A difference counts only when the interval excludes zero **and** the
  sign test clears the threshold; when the two disagree, the report says so.
  Two runs that tie on every common task say that instead of printing `+0.0 pp`.
- **Cost, counted honestly.** Targets accept `price_input` and `price_output`
  (USD per 1M tokens). Reports add `estimated cost` and `cost per solved task`,
  and the console grows a cost column only when something is priced. Token
  accounting now includes discarded over-cap calls and the feedback turn —
  counting only the winning attempt understates the bill.
- **`modelbench card RUN`** writes a 1200×675 SVG scorecard (and a PNG with
  `--png`, via `rsvg-convert`): score, interval, final score, tok/s, tokens,
  cost, suite digest, seed, worst-first categories and a per-task sparkline.
  Self-contained, no external assets, XML-escaped labels.
- **`modelbench leaderboard runs/*`** ranks the runs on your disk instead of
  strangers' submissions. Overlapping intervals share a rank (`1=`), `◆` marks
  the Pareto frontier on score vs token spend, and runs from different suites
  are refused unless `--allow-mixed`. Writes `reports/LEADERBOARD.md`, or
  `--json`.
- **New suite `work-v1` — 4 tasks, 63 assertions, no programming exercises.**
  A fixed-width report built to a 53-column spec, a lenient reader for a
  vendor's almost-JSON dialect, a monthly retention query executed against two
  datasets (so a hardcoded answer fails), and a memo turned into seven
  commitments with verbatim sources. This is the non-coding proof the README
  kept promising: the runner needed no new concept.
- Fixed a duplicated `samples` property on `Run` that silently shadowed the
  first definition.
- JSON `pairwise` entries gain `gap_pp` and `gap_ci_pp`, oriented towards the
  leader, next to the signed `mean_delta_pp` / `delta_ci_pp` (which stay `a - b`).
  Markdown, HTML and console prose now use the oriented pair, so a leader listed
  second no longer prints "+7.2 pp" beside a delta of -7.2.
- The significance branch no longer appends the crude run-to-run noise clause
  when the interval is already tighter than the per-task swing; it says that
  individual tasks can swing more than the gap while its direction holds.
- An all-identical sample (every task the same score) returns a zero-width
  interval deterministically instead of a bootstrap mean that lands one ulp
  off on 3.11, where `sum()` is not compensated — `(0.9, 0.9)` on every
  interpreter, not `0.9000000000000002` on some.
- CI: the matrix now also runs 3.14, `work-v1` is validated and self-tested
  alongside the other two suites, and the actions are on v7 (Node 20 runtime
  deprecation).
- 78 -> 98 tests; 404 -> 467 reference assertions across three suites.

## 1.4.1

- The headline table states `samples / task`. A report read out of context should
  not leave you guessing how many draws each mean is built from — it is the
  number that decides whether any of the deltas mean anything.

## 1.4.0

- **A provisional ranking is not a ranking.** `Pairwise.samples_min` records the
  fewest samples any task carries in either run. Below `--require-samples`
  (default 3) the report prints a "Provisional ranking" banner, retitles the
  per-task column from `winner` to `leader`, and the console verdict says
  `provisional at N sample(s)/task`. `--require-samples 0` turns it off; the
  older two-sample behaviour is `--require-samples 2`.
- `summary.json` gains a top-level `evidence` block
  (`samples_required`, `samples_per_task`, `provisional`) and per-pair
  `noise_pp`, `decisive`, `samples_per_task`, `provisional`, so a CI job can
  refuse to publish a provisional ranking without parsing prose.
- `modelbench run --fail-under SCORE` exits 1 when the mean final task score is
  below the bar (`0.9` and `90` both work). Pair it with `--no-report` for a
  pure regression gate.
- `Run.samples` property: the sample count a run actually carries.
- 74 -> 78 tests (CLI gate, provisional rendering, evidence JSON).

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
