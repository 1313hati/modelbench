<p align="center">
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-3776ab">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="runtime deps" src="https://img.shields.io/badge/runtime%20deps-none-lightgrey">
  <img alt="suites" src="https://img.shields.io/badge/suites-core--v1%20%7C%20core--v2%20%7C%20work--v1-blueviolet">
</p>

```text
  █   █   ███   ████   █████  █      ████   █████  █   █   ████  █   █
  ██ ██  █   █  █   █  █      █      █   █  █      ██  █  █      █   █
  █ █ █  █   █  █   █  █      █      █   █  █      █ █ █  █      █   █
  █ █ █  █   █  █   █  ████   █      ████   ████   █  ██  █      █████
  █   █  █   █  █   █  █      █      █   █  █      █   █  █      █   █
  █   █  █   █  █   █  █      █      █   █  █      █   █  █      █   █
  █   █   ███   ████   █████  █████  ████   █████  █   █   ████  █   █

  a local AI benchmark for coding and more
  llama.cpp · vLLM · Ollama · any OpenAI-compatible endpoint

  ┌─ modelbench ───────────────────────────────────────────────┐
  │ $ modelbench run --target local --samples 2                │
  │                                                            │
  │ suite   core-v2 · 12 tasks · 296 hidden assertions         │
  │ target  local-27b @ 127.0.0.1:8080/v1                      │
  │                                                            │
  │ [ 09/24] t07_thread_queue   s1  23/23 100.0%   41.2s       │
  │ [ 10/24] t08_code_review    s1  14/14 100.0%   22.7s       │
  │ [ 11/24] t09_csv_rfc4180    s1  33/33 100.0%   35.0s       │
  │                                                            │
  │ run complete · 24 records · 18m04s · REPORT.md written     │
  └────────────────────────────────────────────────────────────┘

  install  pipx install modelbench
  source   github.com/1313hati/modelbench
```

**modelbench** is a local AI benchmark. Point it at any OpenAI-compatible
endpoint — llama.cpp, vLLM, Ollama, LM Studio, or a hosted API — and it runs a
fixed suite of graded tasks, keeps every answer, and writes a report you can
defend. Every prompt, raw answer, extracted solution, hidden test and grading
decision is stored on disk, so a score can be re-checked instead of trusted.

Three suites ship today (25 tasks, 467 hidden assertions): two coding suites
and one suite of office work, because the runner is task-agnostic — a suite is
data, not code.

No agent framework, no tool loop, no model-specific glue: one request, one
answer, one grade, one feedback turn. If model A scores 96% and model B 91%,
the difference is the model, not the harness.

```
25 tasks        467 hidden assertions        one equal-weight score per task
a confidence interval on every score       a price on every solve
```

## Table of contents

- [Why another benchmark](#why-another-benchmark)
- [Quickstart](#quickstart)
- [Install](#install)
- [Configure a target](#configure-a-target)
- [Run it](#run-it)
- [Compare models](#compare-models)
- [Is the gap real?](#is-the-gap-real)
- [Did it beat the baseline?](#did-it-beat-the-baseline)
- [What it costs](#what-it-costs)
- [Share a scorecard](#share-a-scorecard)
- [Rank the runs you have](#rank-the-runs-you-have)
- [What is actually measured](#what-is-actually-measured)
- [The suites](#the-suites)
- [Beyond coding](#beyond-coding)
- [Reading a report](#reading-a-report)
- [Seeds, pins and drift](#seeds-pins-and-drift)
- [Why did it fail?](#why-did-it-fail)
- [Write your own suite](#write-your-own-suite)
- [Check the harness without a model](#check-the-harness-without-a-model)
- [Fairness checklist](#fairness-checklist)
- [Limits, honestly](#limits-honestly)
- [Repository layout](#repository-layout)
- [Development](#development)

## Why another benchmark

Most public coding benchmarks fail in one of three ways: they are saturated
(every serious model scores ~100%, so the number carries no signal), they leak
into training data without anyone being able to check, or the harness is a
research script that cannot be run a second time.

`modelbench` optimises for the boring properties instead:

- **Reproducible.** The tasks, hidden tests and reference solutions ship in the
  package. The suite has a content digest that is written into every record.
- **Auditable.** Each answer is kept verbatim next to the code that was
  extracted from it and the grader output that scored it. You can re-grade any
  historical record with `modelbench validate` and the current suite.
- **Fair.** Identical prompts, caps, sampling defaults and feedback text for
  every model. A run that used different settings is visibly different in the
  report.
- **Boring to install.** Python 3.11+, standard library only, zero runtime
  dependencies. Node is needed only for the two JavaScript tasks.

It is deliberately *not* an agent benchmark. There is no browsing, no
repository search, no compiler loop. That keeps it cheap to run and easy to
attribute.

## Quickstart

```bash
git clone https://github.com/1313hati/modelbench
cd modelbench
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

cp modelbench.example.toml modelbench.toml   # then edit the endpoint
modelbench doctor                            # config? endpoint? runtimes?
modelbench run --target local                # 12 tasks × 2 samples
```

A run writes `runs/local-core-v2-<timestamp>/` with `REPORT.md`,
`summary.json`, `results.jsonl` and every raw answer. Around 15–40 minutes on a
single 24 GB GPU at ~60 tok/s; a hosted API is usually faster in wall time and
costs roughly 40–70k output tokens per model.

## Install

```bash
pipx install modelbench          # recommended: isolated CLI
# or
pip install modelbench
# or from a checkout
git clone https://github.com/1313hati/modelbench && cd modelbench
pip install -e ".[dev]"
```

Requirements: Python 3.11+, `sqlite3` (bundled), Node 18+ for the JavaScript
tasks (`t05_async_pool` in `core-v2`, `t4_flatten_js` and `t9_map_limit` in
`core-v1`). `modelbench doctor` tells you what is missing before a run starts.

## Configure a target

A target is one endpoint. The smallest useful config is three lines:

```toml
[targets.local]
base_url = "http://127.0.0.1:8080/v1"
model = "local"
```

Config resolution order: `--config PATH`, `$MODELBENCH_CONFIG`,
`./modelbench.toml`, `./modelbench.local.toml`, then
`~/.config/modelbench/modelbench.toml`. Keep it out of git — the repository's
`.gitignore` already excludes `modelbench.toml` and `*.local.toml`.

`modelbench.example.toml` contains ready-made blocks for llama.cpp, vLLM,
Ollama and a hosted API. The keys that matter most:

| key | meaning |
|---|---|
| `base_url` | endpoint root, usually ending in `/v1` |
| `model` | model id sent in the request body (llama.cpp ignores it, hosted APIs do not) |
| `api_key` / `api_key_env` | literal key, or the name of an env var holding it (preferred) |
| `temperature`, `top_p`, `top_k`, `min_p`, `seed` | sampling; **keep identical across models you compare**. `seed` is pinned to 42 by default |
| `max_tokens`, `retry_cap` | fallback cap, and the cap used for the one retry after `finish_reason=length` |
| `context` | the model's context window. Omit it and the runner asks `/props` (llama.cpp) or `/v1/models`; answers are then clamped so prompt + completion always fit |
| `timeout_s`, `connect_timeout_s`, `max_retries` | HTTP behaviour |
| `headers`, `extra_body` | provider-specific additions merged into the request |
| `start_cmd`, `stop_cmd` | optional shell commands to boot a local server; `{port}` is substituted |
| `ready_timeout_s`, `health_path` | how long to wait for the server, and which path to poll |

Secrets can be referenced as `${VAR}` or `${VAR:-fallback}` anywhere in the
file, so a config can be committed while the key stays in the environment:

```toml
[targets.cloud]
base_url = "https://api.example.com/v1"
model = "some-coder-32b"
api_key_env = "EXAMPLE_API_KEY"
temperature = 0.2               # per-target override of [defaults]
```

Hosted providers often reject unknown sampling keys. Leave `top_k` and `min_p`
unset there — `modelbench` only sends sampling fields that are actually set.

Global defaults live in `[defaults]`: `samples`, `repair`, plus any sampling
key. `[project]` sets the default `suite` and extra `suite_paths`.

## Run it

| command | what it does |
|---|---|
| `modelbench list` | show suites, and the tasks inside one suite |
| `modelbench doctor` | check config, suite, grader runtimes and endpoint reachability |
| `modelbench run` | benchmark one target |
| `modelbench report` | aggregate runs into `REPORT.md`, `REPORT.html` + `summary.json` |
| `modelbench inspect` | what the model actually wrote for one record, and the diff against the reference |
| `modelbench validate` | prove every reference solution still scores 100% |
| `modelbench self-test` | end-to-end run against a mock model, no GPU needed |
| `modelbench mock` | serve reference answers from a fake OpenAI endpoint |
| `modelbench card` | render a run as a 1200×675 SVG/PNG scorecard |
| `modelbench compare` | is a run actually different from the baseline? |
| `modelbench leaderboard` | rank local runs; overlapping intervals share a place |
| `modelbench init-suite` | scaffold a new suite with one example task |

```bash
modelbench doctor --target local          # endpoint reachable? runtimes present?
modelbench run --target local             # full suite, 2 samples, repair on
modelbench run --target local --only t01_weighted_jobs,t03_json_parser --samples 1
modelbench run --target local --resume    # continue an interrupted run
```

`run` prints one line per attempt and streams nothing else — the model's
reasoning stays in the raw logs rather than your terminal:

```text
[  9/24] t07_thread_queue          s1   23/23 100.0%    41.2s  57 t/s
[ 10/24] t08_code_review           s1   14/14 100.0%    22.7s  61 t/s
[ 11/24] t09_csv_rfc4180           s1   33/33 100.0%    35.0s  58 t/s
```

Useful flags:

| flag | effect |
|---|---|
| `--samples N` | independent samples per task (default 2; use ≥3 for close models) |
| `--only`, `--exclude` | comma-separated task ids |
| `--max-tokens`, `--retry-cap` | override the caps from task metadata |
| `--temperature`, `--top-p`, `--top-k`, `--seed` | override sampling for this run (`seed` is sample 1; sample *n* uses `seed+n-1`) |
| `--no-seed` | send no seed at all, to measure an endpoint's own drift |
| `--no-repair` | grade the first answer only |
| `--resume` | skip task/sample pairs already in `results.jsonl` |
| `--order task` | run all samples of a task back-to-back instead of interleaved |
| `--jobs N` | run N task/sample pairs at once (hosted endpoints; a single-slot local server gains nothing) |
| `--out DIR`, `--name LABEL` | where to write, and how the run is labelled |
| `--no-report` | skip `REPORT.md` (write it later with `modelbench report`) |
| `--dry-run` | print the plan — tasks, caps, prompt size, call count, token ceiling — and exit without calling the endpoint |
| `--fail-under SCORE` | exit 1 if the mean final task score lands below SCORE (`0.9` or `90`), for CI gates |
| `--no-html`, `--html PATH` | skip the HTML page, or write it somewhere specific |
| `--allow-missing-runners` | skip tasks whose runtime is absent instead of failing them |
| `--no-manage-server` | ignore `start_cmd`/`stop_cmd` from the config |
| `--fail-fast` | stop on the first task error |

Exit codes: `0` complete, `1` completed with task errors, `2` configuration or
usage error, `130` interrupted (partial results are kept).

## Compare models

Run each model into its own directory, then point the report command at them:

```bash
modelbench run --target local  --name local-27b
modelbench run --target small  --name local-9b
modelbench report runs/local-27b-core-v2-* runs/local-9b-core-v2-*
```

`report` accepts run directories, a `results.jsonl`, or a folder full of runs.
It prints a console comparison, writes `REPORT.md` and `summary.json`, and
uses pairwise deltas on first-attempt task scores:

```text
run          first   final  solved  records  med call     tok/s  tokens
----------  ------  ------  ------  -------  --------  --------  ------
local-27b    99.7%  100.0%   91.7%    24/24     37.6s      58.2   48,201
local-9b     95.1%   97.2%   86.4%    24/24     53.1s      57.0   71,344

task wins: local-27b 4, local-9b 1, ties 7 (mean delta +12.4 pp)
```

Any number of runs can be compared; with more than two, each task shows the
best model instead of a delta. `--json` prints the machine-readable summary
instead of writing files, and `--notes-file` appends your own context to the
report. `--strict` exits 1 if any run is missing records, holds duplicates or
carries task errors — useful as a CI gate. `--html PATH` writes the shareable
page outside the output directory. `--require-samples N` (default 3) sets how
much evidence a winner claim needs before the report stops calling the ranking
provisional. `modelbench run --fail-under 0.9` is the other half of a CI gate:
it benchmarks, writes the report, then exits 1 if the final mean task score is
below the bar.

## Is the gap real?

A suite score is a mean over a dozen tasks. Printed to one decimal it looks
like a measurement; in practice one task flipping moves it by eight points. So
every score now carries a **95% bootstrap confidence interval**, and every
comparison carries a **paired interval plus an exact sign test**:

```text
run          first   95% CI, first      final  solved  samples
----------  ------  ----------------  -------  ------  -------
local-27b    99.7%  98.9–100.0%        100.0%   91.7%        3
local-9b     95.1%   92.6–97.4%         97.2%   86.4%        3

task wins: local-27b 4, local-9b 1, ties 7
mean delta +12.4 pp (95% CI +3.9 to +20.8 pp), two-sided sign test p = 0.375
difference not established — the interval and the sign test disagree
```

The interval resamples **tasks** — the unit the score weights equally — with a
fixed seed, so a CI quoted in a pull request still matches the CI regenerated
from disk a month later. The comparison uses per-task deltas and a sign test,
which assumes nothing about how scores are distributed; with twelve tasks a
t-distribution is a costume, not a measurement.

A gap counts as established only when **both** tests agree: the interval must
exclude zero *and* the sign test must clear the threshold. When they disagree
the report says so. When two runs tie on every task it says that too, instead
of printing a meaningless `+0.0 pp`.

The suite also has a resolution, and it is worth saying out loud: with twelve
tasks the exact sign test needs **ten of them moving the same way** to reach
p < 0.05 (nine gives p = 0.146). A 40-point gap carried by four tasks is not a
finding, however impressive the mean looks. Reports quote that bar next to the
test, so the reader can see what the suite can settle and what it cannot.

## Did it beat the baseline?

`report` shows every model. `compare` answers one question per challenger, and
answers it in a form a script can act on:

```bash
modelbench compare runs/local-27b runs/local-9b runs/hosted-mini
```

```text
baseline  local-27b  99.7% (98.9–100.0%)  core-v2 · 12 tasks · 2 sample(s)

run          score                 gap vs baseline              p (Holm)  verdict
hosted-mini  91.2% (88.4–93.6%)     -8.5 pp (-13.1, -3.9)            0.006  worse
local-9b     95.1% (92.6–97.4%)     -4.6 pp (-9.8, +0.6)             0.375  not established

resolution: with 12 tasks the exact sign test needs 10/12 in the same direction
to reach p < 0.05; anything smaller is not established, whatever the interval says.
```

The p-values are **Holm-adjusted** across the challengers. Testing one baseline
against five models is five chances to be fooled by noise; Holm controls that
family-wise error rate without assuming independence, and without the flat tax
of a Bonferroni multiplier. A comparison that is significant on its own can
stop being significant when it joins a family — that is the correction doing
its job, and `compare` shows both numbers in `--json`.

`--fail-on regression` exits 1 when a challenger is established as worse than
the baseline; `--fail-on unresolved` exits 1 when a comparison settles nothing,
for teams that would rather fail than guess. `--md` prints a table ready for a
PR comment; `--json` is the same verdict for machines.

## What it costs

Most benchmarks publish a score and leave you to discover the bill. Add prices
to a target and the report grows a cost column:

```toml
[[targets]]
name = "hosted"
base_url = "https://api.example.com/v1"
model = "some-model"
price_input = 0.15     # USD per 1M prompt tokens
price_output = 0.60    # USD per 1M completion tokens
```

```text
prompt tokens, total   412,880
estimated cost         $0.41
cost per solved task   $0.037
```

Retries, discarded over-cap calls and the feedback turn are all counted,
because a bill that only counts the winning attempt is fiction. Leave the
prices out and the column disappears — an unpriced run is not a free one.

## Share a scorecard

A report is for reading. A card is the one image that travels without its
footnotes:

```bash
modelbench card runs/local-27b-core-v2-2026-10-19 --title "Qwen3.8-27B" --png
```

`CARD.svg` and `CARD.png` (1200×675) carry the score, its interval, the final
score after feedback, tokens/s, tokens, cost, the suite digest and seed, a
worst-first category breakdown, and a sparkline of every task from worst to
best. The interval is on the card on purpose: if a number is worth posting, the
doubt around it is worth posting too. No external fonts or images, so the SVG
renders anywhere.

## Rank the runs you have

Public leaderboards rank strangers' submissions. This one ranks the directories
on your disk:

```bash
modelbench leaderboard runs/*           # writes reports/LEADERBOARD.md
modelbench leaderboard runs/* --json    # machine-readable
```

Runs whose intervals overlap **share a rank** (`1=`, `2=`), because with a
dozen tasks "94.1% vs 94.6%" is a coin landing heads. A `◆` marks the Pareto
frontier: nobody beats that run on both score and token spend. Mixed suites are
refused by default — two suites are two scales — and `--allow-mixed` prints the
warning and ranks anyway.

## What is actually measured

One **attempt** is one request/response. Its score is

```
attempt score = passed assertions / total assertions
```

A **task score** is the mean over its samples. The **suite score** is the mean
over tasks, so a 47-assertion parser and a 12-assertion scheduling task weigh
the same. A separate pooled *assertion rate* is reported for people who prefer
that view, but it is not the headline.

Every attempt then gets exactly one feedback turn:

1. The model receives its own answer plus the failing assertion names and
   messages — never the hidden test source, never the reference solution.
2. Its revision is graded independently.
3. `final = max(first, repair)`. A model that is right the first time cannot be
   punished for a worse revision.

Other rules that are part of the protocol, not implementation details:

- **Extraction.** The last complete fenced code block wins. An answer that ends
  inside an unclosed fence is salvaged rather than discarded. An answer with no
  fence at all is graded verbatim and flagged `source: raw` in the report.
  Repository tasks are split on `### FILE: path`, and paths that escape the
  workspace are dropped.
- **Token caps.** Each task has its own cap (see the suite table). A
  `finish_reason=length` triggers one retry at `retry_cap` (default 16384); both
  attempts' token usage is recorded, and the discarded one is kept in
  `discarded_calls` so cost is not understated.
- **Repair budget.** The repair turn uses the same cap as the original attempt.
  There is never a second feedback round.
- **Reasoning.** If an endpoint returns `reasoning_content`, it is written to
  the raw log and excluded from grading. Verbosity is measured, not rewarded.
- **Warm-up.** One tiny request is sent before the first graded task, so the
  first task does not pay the model-load cost. Disable with `--no-warmup`.

## The suites

Three suites ship with the package. `core-v2` is the default and the one to use
for comparisons; `core-v1` is short and fast, and mostly useful as a smoke test
because strong models saturate it; `work-v1` is the non-coding proof.

### core-v2 — 12 tasks, 296 assertions

| task | category | cap | checks | what it asks for |
|---|---|---|---|---|
| `t01_weighted_jobs` | algorithms | 8192 | 12 | maximum-profit scheduling over weighted intervals |
| `t02_text_justify` | spec | 6144 | 18 | greedy full justification with exact spacing rules |
| `t03_json_parser` | parsing | 8192 | 47 | a JSON parser written from scratch, correct errors included |
| `t04_sql_report` | sql | 6144 | 42 | one SQLite query producing an exact report table |
| `t05_async_pool` | async | 8192 | 12 | bounded-concurrency async map with retries (Node) |
| `t06_repo_bugfix` | repo | 10240 | 25 | fix a failing multi-file package without breaking its API |
| `t07_thread_queue` | concurrency | 8192 | 23 | a thread-safe bounded FIFO with timed offers |
| `t08_code_review` | review | 8192 | 14 | report every real defect, and no false positives |
| `t09_csv_rfc4180` | parsing | 8192 | 33 | strict RFC 4180 reader and writer |
| `t10_pairs_refactor` | refactor | 8192 | 13 | turn an O(n²) pairing function into a fast, equivalent one |
| `t11_varint_protocol` | binary | 8192 | 32 | a zig-zag varint format and its decoder |
| `t12_ledger_feature` | longcontext | 10240 | 25 | implement two features across an existing package |

### work-v1 — 4 tasks, 63 assertions

The non-coding suite, and the answer to "is this just another code benchmark".
None of these is a programming exercise in disguise: `t01` is a layout spec to
the character, `t04` is reading comprehension with exact quotes. All four are
graded by deterministic checkers, so no judge model is involved.

| task | category | cap | checks | what it asks for |
|---|---|---|---|---|
| `t01_fixed_width_report` | instruction | 4096 | 15 | a 53-column sales report, sorted, rounded and truncated to spec |
| `t02_json_repair` | parsing | 6144 | 18 | a reader for a vendor's almost-JSON dialect, errors included |
| `t03_sql_cohort` | sql | 3072 | 14 | monthly retention; run against a second, unpublished dataset |
| `t04_memo_extraction` | extraction | 4096 | 16 | seven commitments out of a memo, with verbatim source sentences |

`t03` is deliberately executed twice, against two datasets, so a query that
hardcodes the first answer fails the second time. `t02` checks that the module
does not reach for `json` or `eval` — the point is the parser.

### core-v1 — 9 tasks, 108 assertions

Shorter single-file tasks (merge intervals, duration parsing, LRU cache, JS
array flattening, debugging, sliding-window duplicates, query parsing, chunk
reassembly, bounded async map). Kept because it is useful for a quick
sanity check of a new endpoint, and because it makes regressions in the harness
obvious.

## Beyond coding

Code is the easiest thing to grade exactly without a judge model: a hidden
test either passes or it does not. That is why the first two suites are code.

It is not the only thing. `work-v1` ships four tasks of ordinary desk work —
copy a table into a fixed layout, repair an export, write one retention query,
turn a memo into commitments — and the runner did not need a new concept to
score them. A suite is a directory of prompts, hidden tests and reference
answers; `meta.json` only describes caps, categories and how to run its grader.
Anything with a deterministic checker fits the same commands and the same
report:

- **structured output** — exact JSON, schema conformance, strict CSV or SQL;
- **transformation** — normalise this export, produce that table, extract these records;
- **instruction following** — width, order, rounding and refusal rules checked mechanically;
- **retrieval-style answering** — a fixed expected answer compared exactly.

What it will not do is grade open-ended prose. "Which model writes nicer
documentation" needs a judge model, and a judge model is a second opinion, not
a measurement — modelbench stays out of that business on purpose.

If you publish a suite, its reference solutions must pass every assertion
(`modelbench validate`) before the numbers it produces mean anything.

## Reading a report

Each report exists in three formats, written together:

| file | for |
|---|---|
| `REPORT.md` | reading in the repo, pasting into a PR or an issue |
| `REPORT.html` | sharing: one self-contained page, opens offline, no assets |
| `summary.json` | dashboards, CI gates, your own plotting |

The HTML page is the pleasant one: at-a-glance cards, a sortable per-task
matrix with score bars and deltas, per-category scores, sample stability,
failure signatures, provenance, integrity, and the commands that reproduce it.
It is a single file with inline CSS and a ~20-line sort script — no CDN, no
fonts, no network access, and it renders the same from disk in five years.

`REPORT.md` has these sections, in this order:

- **Verdict** — one sentence naming the leader and the margin, plus whether the
  difference is established, inside the noise, or unprovable because both runs
  scored identically.
- **Headline** — records vs expected, first/final scores with their 95%
  intervals, assertion rate, solved rate, repair behaviour, sample stability,
  wall time, tokens, estimated cost, cost per solved task.
- **Per task** — the same scores per task with deltas and a task-win count.
  This is where you see *which kind* of work a model is bad at.
- **Per category** — the same data grouped by category.
- **Where it fails** — failing assertions grouped by name, so "fails
  `handles_negative_input` in both samples of two tasks" is visible as a
  systematic gap rather than a percentage.
- **Provenance** — endpoint, served model id, samples, suite digest.
- **Integrity** — missing records, duplicates, cap hits, graders without a
  `RESULT` line, salvage operations.

Two lines in the headline deserve a habit:

- **tasks where samples differ** — if the two samples of a task disagree, that
  task's mean is a coin flip dressed as a number. A model that scores 90% with
  five unstable tasks is not better than one that scores 89% with none; it is
  noisier.
- **mean within-task spread** — the average gap between best and worst sample
  of the same task. Under ~5 pp the suite is behaving deterministically for that
  model; above ~20 pp you need more samples before comparing anything.
- **95% CI, first · final** — the interval a reader should quote instead of the
  point estimate. With twelve tasks it is usually wide; that width is the
  benchmark being honest, not the model being uncertain.

The integrity section is the one to read first. A 99% score from a run with six
missing records is not a 99% score. `modelbench` never silently drops a failed
task: it writes `errors.log`, keeps the successful records, and marks the run
incomplete. `modelbench report --strict` turns that into exit code 1, which is
what you want in CI.

## Seeds, pins and drift

The same model on the same endpoint can swing several points between runs.
That is not the model changing its mind, it is sampling: a one-word difference
in a generated token can flip an entire assertion, and with `temperature` above
zero the sampler is free to pick it on one run and not the next.

modelbench pins the sampler by default, because a comparison of two runs that
were sampled differently is not a comparison of two models:

| setting | default | note |
|---|---|---|
| `temperature` | `1.0` | recorded in `run.json`, printed before the first request |
| `top_p` | `0.95` | — |
| `seed` | `42` | **sample *n* is sent with `seed + n - 1`** |
| `samples` | `2` | independent prompts-with-different-seeds, not reruns of one |

The per-sample offset matters. Two samples sent with the identical seed are one
sample counted twice: the stability rows would read `0.0 pp spread` for every
task and quietly hide the variance you were trying to measure. Sample 1 goes out
with seed 42, sample 2 with 43 — independent draws from a reproducible run.

Override for one run with `--temperature`, `--top-p`, `--top-k`, `--seed`. To
measure how much an endpoint drifts *without* a seed, pass `--no-seed`: nothing
is sent, the run header and the report say `seed not pinned`, and you have
bought honesty at the price of not being able to reproduce the run exactly.

What the report does with this:

- **Provenance** lists temperature and seed per run, and `not pinned` in red
  when a run has no seed;
- **Sample stability** compares the samples of each task, so a model that is
  noisy on its own shows up as noisy rather than as "89%";
- **Comparing runs sampled differently** puts a warning above the fold naming
  the fields that differ (`temperature: 0.2 vs 1.0`, `seed: 42 vs not set`) and
  tells you to re-run before reading a winner into it;
- **A gap smaller than the noise is reported as noise.** The comparison measures
  how far each task moved between its own samples and, if the mean delta is
  inside that, says so instead of naming a winner — a per-task `≈` marks the
  individual flips.

A practical protocol for a comparison you intend to publish:

```bash
# same suite, same sampling, seeds pinned, three samples
modelbench run --target a --samples 3 --out runs/a
modelbench run --target b --samples 3 --out runs/b
modelbench report runs/a runs/b --strict
```

**Three samples is the floor for a claim, and the report enforces it.** The noise
figure is built from how far each task moved between its own samples; with two
samples that is a range across two points, which can read 0 pp or 100 pp and is
not an estimate of anything. So unless a pair of runs carries
`--require-samples N` (default 3) samples per task, the report prints a
**Provisional ranking** banner, retitles the per-task column `leader` instead of
`winner`, and `summary.json` records `evidence.provisional: true`. Relax it with
`--require-samples 2` when you only want a smoke comparison, or tighten it to 5
for a publishable one.

If the two runs come out within a point of each other, raise `--samples` or
accept that the task suite cannot separate them. Do not lower the temperature
until the winner appears — that is the modelbench equivalent of p-hacking.

Local backends are not equally honest about seeds. llama.cpp with a fixed seed,
a warm cache and greedy-ish sampling (`top_k` small, `temperature` low) is close
to deterministic; many hosted providers ignore `seed` entirely or only promise
"best effort". The sample-stability rows are how you find out which kind you are
talking to before you publish anything.

## Why did it fail?

A report tells you which task lost points. `inspect` tells you why, without
opening JSON by hand:

```bash
modelbench inspect runs/local-27b-core-v2      # triage: what lost points
modelbench inspect runs/local-27b-core-v2 --task t03_json_parser --sample 2
```

The triage view lists every record that scored below full marks, worst first,
with the first failing assertion:

```
# first line: <label> <path>, then how many records lost nothing
task                     s  score    first failing assertion
------------------------------------------------------------
t03_json_parser          1   24/31  FAIL rejects_trailing_comma: expected ValueError, got dict
t07_streaming_parser     2    0/31  <no RESULT line>: ModuleNotFoundError: No module named 'sol'
…                                   # worst first, up to 40 rows
```

One record in full gives you the prompt's title, the seed, the finish reason,
the failing assertions, what the model actually wrote, and a unified diff
against the task's reference solution:

```
t03_json_parser  sample 2  [Lenient JSON parser]
run      runs/local-27b-core-v2  (local-27b-core-v2, suite core-v2)
kind     file / py   category parsing
seed     43   served id Qwen3.8-27B
score    24/31 first   final 100.0% (solved)
call     finish=stop  tokens=…  ttft=…s  total=…s  source=fence

first attempt — failing assertions:
  FAIL rejects_trailing_comma: expected ValueError, got dict

what the model wrote (runs/local-27b-core-v2/s2/sol):
--------------------------------------------------------------------
def parse(text):
    …
--------------------------------------------------------------------

diff against the reference (src/modelbench/suites/core-v2/tasks/t03_json_parser/ref):
--------------------------------------------------------------------
--- reference
+++ model
@@ -14,7 +14,7 @@
-    if text.rstrip().endswith(","):
-        raise ValueError("trailing comma")
+    # trailing commas are tolerated
```

That last block is the point: a diff is faster to read than a score. `--context`
controls how much surrounding code you get, `--full` prints the whole answer,
`--json` drops the formatted view for the raw record, and `--suite PATH` points
at a suite that is not in this installation.

## Write your own suite

A suite is a directory:

```text
suites/my-suite/
  suite.toml                 # id, name, version, description
  prompt.md                  # optional: override the prompt wrapper
  tasks/
    my_task/
      task.md                # exactly what the model sees
      meta.json              # category, kind, lang, caps, checks
      tests/test_my_task.py  # hidden grader
      ref/solution.py        # reference answer, must score 100%
      files/                 # repo tasks only: starting workspace
```

`modelbench init-suite my-suite` scaffolds exactly this, with a working
example. Then:

```bash
modelbench validate --suite ./my-suite          # refs must pass every assertion
modelbench run --suite ./my-suite --samples 1 --target local
```

Point `[project] suite_paths` at the parent directory to resolve suites by id,
or pass `--suite ./path` directly.

### `meta.json`

| key | default | meaning |
|---|---|---|
| `id` | directory name | task id |
| `title` | id | human-readable name used in reports |
| `category` | `misc` | grouping in the report |
| `kind` | `file` (or `repo` when `files/` exists) | single-file answer, or a workspace of files |
| `lang` | grader extension | `py`, `js`, `sql`, ... determines the expected file type |
| `max_tokens` | 8192 | per-task cap, clamped down when the model's context cannot hold it |
| `retry_cap` | target default | override for the retry after `length` |
| `timeout` | 180 | seconds before the grader is killed |
| `checks` | required | the assertion count for this task. It is the **floor** of the denominator, and `modelbench validate` fails unless the reference solution reaches exactly this many checks |
| `tier` | `core` | `core` or `stretch`; `--tier core` runs a subset a small model can finish |
| `min_ctx` | 0 | context tokens the task needs at all; tasks above the model's window are skipped with a warning instead of failing obscurely |
| `test` | auto-detected | explicit path to the grader script |
| `runner` | inferred from extension | `python`, `node` or `bash` |

### The grader contract

A grader is any script that receives the solution path as `argv[1]` and prints
exactly one final line:

```text
RESULT <passed>/<total>
```

Failures are printed as `FAIL <name>: <message>`; those lines — and only those —
are what the model sees in a repair turn. Individual checks must not abort the
grader: a crash in one assertion should cost one point, not the whole task.

`modelbench.tasklib.harness` provides that:

```python
from harness import Checks, solution_arg

C = Checks()
mod = load_module(solution_arg())          # your loader
C.eq("handles negative", mod.f(-3), 3)
C.check("raises on empty", lambda: mod.f(""))
C.report()                                  # prints RESULT p/t
```

The denominator is the task's declared `checks`, not whatever number the grader
reached. A grader that dies after six of forty-seven checks scores 6/47, not
6/6: a crash may never shrink the denominator, because that would reward a
model for failing early and make two models' scores incomparable.

Grader scripts run with the task directory as the working directory and
`modelbench/tasklib` on `PYTHONPATH`, so `from harness import Checks` works
without installation. For `kind = "repo"`, `argv[1]` is a copy of `files/` with
the model's edits applied.

## Check the harness without a model

Two commands make the benchmark testable on a laptop with no GPU:

```bash
modelbench validate                # every reference solution scores 100%
modelbench self-test               # full end-to-end run against a mock model
modelbench self-test --keep        # ... and keep the run directory to look inside
```

`self-test` starts a local mock endpoint that streams the reference answers,
runs the complete suite through the real client, extractor, grader and report
writer, and then deliberately exercises the two failure paths (token-cap retry,
repair turn). It is the same thing CI runs, and it takes about a minute:

```text
1. reference solutions        12/12 perfect
2. mock model, full suite     12/12 records, every answer 100%, report written
3. failure paths              cap retry recorded, repair turn scored below 100%
SELF-TEST PASSED
```

With `--keep` it prints the temporary directory, so you can open `REPORT.html`
and see exactly what a finished report looks like before spending an hour on a
real model.

`modelbench mock` exposes the same server on a port if you want to poke at it
with `curl` or test a client of your own.

## One suite, any model size

The same 12 tasks should be runnable on a 4B model with an 8k window and a 70B
model with 128k. Three mechanisms make that true:

- **Context discovery.** The runner asks `/props` (llama.cpp) or `/v1/models`
  (vLLM and friends) for the loaded window; `context = 32768` in the config
  overrides it. A run records what it found in `run.json`.
- **Budget clamping.** Every answer cap is lowered to fit the remaining window,
  so a small model gets a smaller answer instead of an HTTP 400. A task whose
  prompt cannot fit at all is skipped with a warning, not graded as a failure.
- **Tiers.** Tasks carry `tier = core|stretch`. `--tier core` runs only the half
  a small model can finish; the report prints a score per tier when a run mixes
  them, so a 40% overall and a 65% core score are both visible.

Each attempt also carries a `protocol` verdict — `ok`, `empty_answer`,
`unparseable`, `grader_crash` or `truncated`. The score alone cannot tell "wrote
the wrong function" from "never produced a gradeable answer"; the verdict can,
and the report counts them next to the score.

## Fairness checklist

Before publishing a comparison, confirm:

- [ ] every model used the **same config** (sampling, caps, repair on/off);
- [ ] both runs sent a **pinned seed** with the same base (the report warns you when they did not);
- [ ] the suite **digest** in each report matches;
- [ ] `records / expected` is complete for every run, or the gap is stated;
- [ ] samples ≥ 2, ideally 3, when the gap between models is under ~3 points;
- [ ] local servers ran with the same context size (or the difference is stated) and the same reasoning mode;
- [ ] `protocol failures` is explained: an `empty_answer` row is a format result, not a coding one;
- [ ] no model was given extra turns, tools, or a different prompt wrapper;
- [ ] the endpoint reported no truncation (`answers cut by token cap`).

A 1–2 point difference on 12 tasks is noise. Read the per-task table: a model
that loses one task by 100% is telling you something specific, which is more
useful than the mean.

## Limits, honestly

- **Contamination.** The tasks and reference solutions are public. A model
  trained after this was published may have seen them. Treat the scores as a
  regression check, not as a leaderboard claim, and keep a private suite
  (`--suite ./private`) for real evaluation.
- **Single-turn, no tools.** This measures specification-following and
  self-contained code generation, not agentic engineering. A model that is
  excellent inside an editor loop can score poorly here, and vice versa.
- **Language scope.** Python, JavaScript, SQLite. No Rust, Go, C++ or frontend
  tasks yet.
- **Coarse granularity.** Twelve tasks means one bad task costs ~8 points of
  suite score. That is why every score is printed with its interval: the suite
  cannot separate models that differ by a point or two, and now says so instead
  of ranking them by noise.
- **Caps bias toward brevity.** A very verbose reasoner can be cut off. The
  retry and `finish_reason` accounting make this visible rather than silent.
- **One grader, one opinion.** Tests are hand-written assertions, not property
  tests or fuzzing. They are strict about the specified behaviour and silent
  about everything else, which occasionally means a correct-but-different
  answer loses a point.

## Repository layout

```text
src/modelbench/
  cli.py           command line surface
  config.py        TOML targets, env expansion
  client.py        streaming chat client (urllib, no SDK)
  prompts.py       prompt wrappers and the repair message
  tasks.py         suite/task discovery, validation, solution materialisation
  grader.py        runs the hidden tests, parses RESULT
  runner.py        sample × task loop, retries, records
  report.py        metrics, pairwise comparison, markdown/JSON reports
  stats.py         bootstrap intervals and the exact sign test
  card.py          the 1200×675 SVG scorecard
  leaderboard.py   ranks local runs, ties overlapping intervals
  extraction.py    code-fence and ### FILE: extraction
  mockserver.py    reference-answer server used by self-test
  tasklib/harness.py   assertion helpers for graders
  suites/          core-v1, core-v2, work-v1
scripts/make_banner.py   regenerates assets/banner.txt and the JPG
tests/             pytest: extraction, config, grading, reporting, CLI
```

Run directories are self-describing:

```text
runs/local-core-v2-20260101-120000/
  run.json            manifest: target, suite digest, sampling, status
  results.jsonl       one JSON record per task × sample
  s1/raw/<task>.txt   verbatim model output (plus .repair.txt)
  s1/sol/<task>.solution.py
  errors.log          only present when something failed
  REPORT.md, REPORT.html, summary.json
  CARD.svg            only after `modelbench card`
```

## Development

```bash
pip install -e ".[dev]"
pytest                     # unit tests, no network
modelbench self-test       # end-to-end, no model
modelbench validate        # every reference must still pass
python scripts/make_banner.py --text assets/banner.txt --jpg assets/banner.jpg
```

Adding a task means adding a directory with `task.md`, `meta.json`, a grader
and a reference solution, then running `modelbench validate --only <task>`.
Pull requests that add a task must keep all existing reference solutions at
100%.

## License

MIT — see [LICENSE](LICENSE).
