# Changelog

## 2.2.0

The release where a score means the same thing on an 8k laptop model and a 128k
server model, and where "failed" stops hiding "never answered".

- **The denominator is the task's declared `checks`.** A grader that stops
  after 6 of 47 checks now scores 6/47, not 6/6. Previously the reached count
  became the denominator, so a crash that skipped most of a suite could read as
  near-perfect; totals also differed between models on the same suite (187 vs
  264 assertions on core-v2), which made `assertion_rate` incomparable. Both
  numbers are recorded: `total` and `reported_total`.
- **`modelbench validate` now fails when declared and reached checks disagree.**
  The reference solution must hit every declared check, or the suite is
  rejected with `meta.checks=N but the grader reached M`. Found and fixed one
  such drift in the `init-suite` scaffold (declared 7, real 6).
- **Context discovery and budget clamping.** `context` in a target config, or
  `/props` and `/v1/models` on the server, tells the runner the window; answer
  caps are lowered to fit it and `run.json` records what was found. Tasks can
  declare `min_ctx`; those that cannot fit are skipped with a warning instead
  of failing as if the model were wrong.
- **Tiers.** `meta.json` gains `tier = core|stretch`; `--tier core` runs the
  subset a small model can finish, and reports show a score per tier when a run
  mixes them.
- **A protocol verdict per attempt.** `ok`, `empty_answer`, `unparseable`,
  `grader_crash`, `truncated`, stored on every attempt and counted in the
  report. A thinking model that spends its whole budget in the reasoning
  channel is now visible as an empty answer, not as bad code.
- **Repair turns echo reasoning when content is empty.** Previously the
  assistant turn read `(empty)`, throwing away the only draft a thinking model
  produced.
- core-v2 tasks carry `tier` and `min_ctx`. Their `meta.json` changed, so the
  suite digest changed too: comparing a 2.2 run with a 2.1 run needs
  `--allow-mixed`, and the scores themselves are unaffected.
- 105 -> 122 tests.

## 2.1.0

The release where the benchmark stops asking the reader to hold a p-value in
their head and answers the only question a model comparison actually has.

- **`modelbench compare BASELINE RUN...`** — one verdict per challenger:
  `better`, `worse`, `not established` or `identical`, with the gap, its 95%
  interval, the win/loss/tie split and the p-value that produced the verdict.
  `--fail-on regression` turns it into a CI gate; `--fail-on unresolved`
  refuses to pass on a coin flip. `--json` and `--md` for machines and PRs.
- **Holm-Bonferroni across the family.** Testing one baseline against five
  challengers is five chances to be fooled by noise. `compare` adjusts the
  p-values and keeps both the raw and the adjusted number: a comparison that
  stands alone can correctly stop being significant when it joins a family.
- **The report states its own resolution.** With 12 tasks the exact sign test
  needs 10 in one direction to reach p < 0.05; 9 gives p = 0.146. That bar is
  printed next to the test, so a mean carried by four tasks is visible as such
  instead of looking like a finding.
- **`--jobs N`** runs task/sample pairs concurrently. The pairs were already
  independent — each owns its sample directory — and the results file, error
  log and progress line are serialised through a lock. The default stays 1,
  because a single-slot local server gains nothing from a queue of requests.
- `sign_test_min_wins()` and `holm()` in `stats.py`, both tested against known
  values (10/12, 6/6, 5/None) instead of against their own output.
- 98 -> 105 tests.

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
