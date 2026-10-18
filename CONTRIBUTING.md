# Contributing

Thanks for taking a look. The most useful contributions are **new tasks**,
**new suites** and **grader hardening** — anything that makes a score harder to
fake.

## Ground rules

- Every task needs a reference solution in `ref/` that scores **100%**.
  `modelbench validate --suite <suite>` must pass before a PR is reviewed.
- Graders must be deterministic, offline and fast. No network, no clock, no
  randomness without a fixed seed, no writes outside the task directory.
- No task may depend on a specific model, vendor or tokenizer.
- Keep the prompt self-contained. The model sees `task.md` and nothing else.
- Hidden tests stay hidden from the prompt: never restate the assertions in
  `task.md`.

## Development setup

```bash
git clone https://github.com/1313hati/modelbench
cd modelbench
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
modelbench validate
modelbench self-test
```

`modelbench self-test` runs the whole pipeline against the built-in mock model,
so it works on a machine with no GPU and no API key.

## Adding a task

```bash
modelbench init-suite scratch --dir /tmp/scratch   # scaffold to copy from
mkdir -p src/modelbench/suites/core-v2/tasks/t13_my_task/{tests,ref}
```

1. `task.md` — exactly what the model sees. State the signature, the input
   domain, the edge cases and the one thing that is easy to get wrong. No
   hints about the tests.
2. `meta.json` — `id`, `title`, `category`, `kind`, `lang`, `max_tokens`,
   `timeout`, `checks`.
3. `tests/test_my_task.py` — import the solution, assert behaviour, end with
   `C.report()`. Use `modelbench.tasklib.harness.Checks` so failures are
   collected instead of aborting the grader.
4. `ref/` — the reference answer, handwritten, not model-generated.
5. Validate:

```bash
modelbench validate --suite core-v2 --only t13_my_task
modelbench run --suite core-v2 --only t13_my_task --samples 1 --target local
```

### Writing good assertions

- Aim for 10–50 independent checks: enough to make partial credit meaningful,
  few enough that one bug does not cost the whole task.
- Test behaviour, not implementation. No assertions on function internals,
  logging text or formatting the prompt did not ask for.
- Include the edge cases a competent engineer would think of: empty input,
  negative numbers, unicode, ordering, error types.
- One `C.check` per property, with a name that reads as the property
  (`"rejects negative width"`), because that name is what the model sees when
  it gets a repair turn.

## Adding a suite

A suite is a directory with `suite.toml`, `prompt.md` (optional) and `tasks/`.
Add it under `src/modelbench/suites/<id>/` and it ships with the package; add
`[project] suite_paths` in your own config to keep private suites out of git.

Suites do not have to be about code. Anything a deterministic checker can
grade — structured output, transformations, format compliance — works with the
same layout. Suites that need a judge model are out of scope.

## Pull request checklist

- [ ] `pytest` passes
- [ ] `modelbench validate --suite core-v1` and `--suite core-v2` pass
- [ ] `modelbench self-test --suite core-v2` passes
- [ ] new tasks have a reference solution and a `checks` count in `meta.json`
- [ ] no secrets, private endpoints or absolute home paths in committed files
- [ ] `README.md` / `CHANGELOG.md` updated when behaviour changes

## Reporting a bad task

If a task is ambiguous, unfair or has a bug in its tests, open an issue with
the run directory and the record's `task` + `sample`. The raw answer and the
grader output are usually enough to decide whether the task or the model is
wrong.
