"""Aggregation and reporting.

A report is intentionally more than a score table: it records where the numbers
came from (served model, endpoint, suite digest, sampling), how complete the run
was, and where the model's answer had to be salvaged by the extractor.  Those
details are what make a comparison believable — and what let someone else
reproduce it months later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from . import __version__
from .util import (
    column_table,
    int_fmt,
    mean,
    median,
    now_iso,
    p90,
    pct,
    read_json,
    read_jsonl,
    stdev,
    write_json,
)

MISSING = "—"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
@dataclass
class Run:
    label: str
    path: Path
    header: dict
    records: list[dict]

    @property
    def tasks(self) -> list[str]:
        listed = (self.header.get("suite") or {}).get("tasks")
        if listed:
            return list(listed)
        return sorted({r["task"] for r in self.records})

    @property
    def samples(self) -> int:
        if self.header.get("samples"):
            return int(self.header["samples"])
        seen = {int(r.get("sample") or 1) for r in self.records}
        return max(seen) if seen else 1

    @property
    def suite_id(self) -> str:
        return str((self.header.get("suite") or {}).get("id") or (self.records[0].get("suite") if self.records else "") or "")


def load_run(path: str | Path) -> Run:
    path = Path(path).expanduser()
    if path.is_file():
        results = path
        root = path.parent
    else:
        results = path / "results.jsonl"
        root = path
    if not results.is_file():
        raise FileNotFoundError(f"no results.jsonl in {root}")
    records = read_jsonl(results)
    if not records:
        raise ValueError(f"{results} is empty")
    header = read_json(root / "run.json", default={}) or {}
    label = str(
        (header.get("target") or {}).get("name")
        or records[0].get("target")
        or records[0].get("model")
        or root.name
    )
    # A resumed run may contain records from different labels; keep them visible.
    labels = {str(r.get("target") or r.get("model")) for r in records}
    if len(labels) > 1:
        label = f"{label} (+{len(labels) - 1})"
    return Run(label=label, path=root, header=header, records=records)


def load_runs(paths: Iterable[str | Path]) -> list[Run]:
    runs = [load_run(path) for path in paths]
    if not runs:
        raise ValueError("no runs given")
    labels: dict[str, int] = {}
    for run in runs:
        labels[run.label] = labels.get(run.label, 0) + 1
        if labels[run.label] > 1:
            run.label = f"{run.label}#{labels[run.label]}"
    return runs


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def task_map(records: Sequence[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for record in records:
        out.setdefault(str(record["task"]), []).append(record)
    return out


def total_tokens(record: dict) -> int:
    total = 0
    for key in ("first", "repair"):
        attempt = record.get(key) or {}
        total += int(attempt.get("completion_tokens") or 0)
        for extra in attempt.get("discarded_calls") or []:
            total += int(extra.get("completion_tokens") or 0)
    return total


def run_metrics(run: Run) -> dict:
    records = run.records
    per_task = task_map(records)
    first_task_means = [mean([r["first"]["score"] for r in recs]) for recs in per_task.values()]
    final_task_means = [mean([r["final_score"] for r in recs]) for recs in per_task.values()]
    solved_first = [1.0 if r["first"]["solved"] else 0.0 for r in records]
    solved_final = [1.0 if r.get("final_solved") else 0.0 for r in records]
    repairs = [r for r in records if r.get("repair")]
    improved = [r for r in repairs if r["repair"]["score"] > r["first"]["score"]]
    repaired_solved = [r for r in repairs if r["repair"]["solved"]]
    walls = [r["first"].get("total_s") or 0.0 for r in records]
    tps = [r["first"]["tok_per_s"] for r in records if r["first"].get("tok_per_s")]
    ttfts = [r["first"].get("ttft_s") for r in records if r["first"].get("ttft_s")]
    tokens = [r["first"].get("completion_tokens") for r in records if r["first"].get("completion_tokens")]
    passed = sum(r["first"]["passed"] for r in records)
    assertions = sum(r["first"]["total"] for r in records)
    sources: dict[str, int] = {}
    for record in records:
        source = str(record["first"].get("source") or "?")
        sources[source] = sources.get(source, 0) + 1
    errors = sum(1 for r in records if r.get("error"))
    return {
        "records": len(records),
        "tasks": len(per_task),
        "samples": run.samples,
        "expected": len(run.tasks) * run.samples,
        "missing": missing_pairs(run, per_task),
        "duplicates": duplicate_pairs(records),
        "first_score": mean(first_task_means),
        "first_sd": stdev(first_task_means),
        "final_score": mean(final_task_means),
        "final_sd": stdev(final_task_means),
        "assertions_passed": passed,
        "assertions_total": assertions,
        "assertion_rate": (passed / assertions) if assertions else 0.0,
        "solved_first": mean(solved_first),
        "solved_final": mean(solved_final),
        "repairs": len(repairs),
        "improved": len(improved),
        "repaired_solved": len(repaired_solved),
        "median_call_s": median(walls),
        "p90_call_s": p90(walls),
        "median_tps": median(tps),
        "median_ttft": median(ttfts) if ttfts else None,
        "median_tokens": median(tokens) if tokens else None,
        "total_tokens": sum(total_tokens(r) for r in records),
        "wall_s": sum(r.get("wall_s") or 0.0 for r in records),
        "truncated": sum(1 for r in records if r["first"].get("finish_reason") == "length"),
        "no_result": sum(1 for r in records if r["first"].get("no_result_line")),
        "sources": sources,
        "errors": errors,
    }


def missing_pairs(run: Run, per_task: dict[str, list[dict]] | None = None) -> list[dict]:
    per_task = per_task or task_map(run.records)
    missing = []
    for task in run.tasks:
        present = {int(r.get("sample") or 1) for r in per_task.get(task, [])}
        for sample in range(1, run.samples + 1):
            if sample not in present:
                missing.append({"task": task, "sample": sample})
    return missing


def duplicate_pairs(records: Sequence[dict]) -> list[dict]:
    seen: dict[tuple[str, int], int] = {}
    for record in records:
        key = (str(record["task"]), int(record.get("sample") or 1))
        seen[key] = seen.get(key, 0) + 1
    return [{"task": task, "sample": sample, "count": count} for (task, sample), count in seen.items() if count > 1]


def per_task_metrics(run: Run) -> dict[str, dict]:
    out = {}
    for task, records in sorted(task_map(run.records).items()):
        out[task] = {
            "category": records[0].get("category") or "",
            "n": len(records),
            "first": mean([r["first"]["score"] for r in records]),
            "final": mean([r["final_score"] for r in records]),
            "solved_first": mean([1.0 if r["first"]["solved"] else 0.0 for r in records]),
            "solved_final": mean([1.0 if r.get("final_solved") else 0.0 for r in records]),
            "assertions": [sum(r["first"]["passed"] for r in records), sum(r["first"]["total"] for r in records)],
            "median_s": median([r["first"].get("total_s") or 0.0 for r in records]),
            "tokens": int(mean([r["first"].get("completion_tokens") or 0 for r in records])),
        }
    return out


def per_category_metrics(run: Run) -> dict[str, dict]:
    buckets: dict[str, list[dict]] = {}
    for record in run.records:
        buckets.setdefault(str(record.get("category") or "misc"), []).append(record)
    out = {}
    for category, records in sorted(buckets.items()):
        by_task = task_map(records)
        out[category] = {
            "n": len(records),
            "tasks": len(by_task),
            "first": mean([mean([r["first"]["score"] for r in recs]) for recs in by_task.values()]),
            "final": mean([mean([r["final_score"] for r in recs]) for recs in by_task.values()]),
        }
    return out


@dataclass
class Pairwise:
    a: str
    b: str
    common: list[str]
    wins_a: int
    wins_b: int
    ties: int
    mean_delta_pp: float
    rows: list[dict]


def pairwise(a: Run, b: Run) -> Pairwise:
    ta, tb = per_task_metrics(a), per_task_metrics(b)
    common = sorted(set(ta) & set(tb))
    rows, wins_a, wins_b, ties = [], 0, 0, 0
    for task in common:
        da, db = ta[task]["first"], tb[task]["first"]
        delta = (da - db) * 100
        if abs(delta) < 0.05:
            winner = "tie"
            ties += 1
        elif delta > 0:
            winner = a.label
            wins_a += 1
        else:
            winner = b.label
            wins_b += 1
        rows.append(
            {
                "task": task,
                "category": ta[task]["category"],
                "a": da,
                "b": db,
                "delta_pp": delta,
                "winner": winner,
            }
        )
    return Pairwise(
        a=a.label,
        b=b.label,
        common=common,
        wins_a=wins_a,
        wins_b=wins_b,
        ties=ties,
        mean_delta_pp=mean([r["delta_pp"] for r in rows]) if rows else 0.0,
        rows=rows,
    )


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _signed_pp(value: float) -> str:
    if abs(value) < 0.05:
        return "0.0"
    return f"{value:+.1f}"


def render_markdown(
    runs: Sequence[Run],
    title: str | None = None,
    notes: str | None = None,
    generated: str | None = None,
) -> str:
    metrics = [run_metrics(run) for run in runs]
    labels = [run.label for run in runs]
    pairs = [pairwise(runs[i], runs[j]) for i in range(len(runs)) for j in range(i + 1, len(runs))]
    suite_ids = {run.suite_id for run in runs}
    title = title or ("modelbench — " + " vs ".join(labels))
    lines: list[str] = [f"# {title}", ""]

    if len(runs) == 1:
        m = metrics[0]
        lines += [
            f"Single run on suite `{runs[0].suite_id}`: **{pct(m['first_score'])}** mean first-attempt "
            f"task score, {pct(m['solved_first'])} of attempts fully solved before feedback.",
            "",
        ]
    else:
        best = max(range(len(runs)), key=lambda i: metrics[i]["first_score"])
        lead = sorted(range(len(runs)), key=lambda i: metrics[i]["first_score"], reverse=True)
        line = (
            f"**{labels[lead[0]]}** leads on first-attempt quality "
            f"({pct(metrics[lead[0]]['first_score'])} vs {pct(metrics[lead[1]]['first_score'])}"
        )
        if len(runs) > 2:
            line = f"**{labels[best]}** leads on first-attempt quality ("
            line += ", ".join(f"{labels[i]} {pct(metrics[i]['first_score'])}" for i in lead) + ")"
        else:
            line += ")"
        pair = next((p for p in pairs if p.a == labels[lead[0]] or p.b == labels[lead[0]]), None)
        if pair and len(runs) == 2:
            first = pair.a == labels[lead[0]]
            wins = pair.wins_a if first else pair.wins_b
            other = pair.b if first else pair.a
            line += f", winning {wins} of {len(pair.common)} tasks against {other} ({pair.ties} tie(s)); "
            line += (
                f"after one feedback turn it is {pct(metrics[lead[0]]['final_score'])} vs "
                f"{pct(metrics[lead[1]]['final_score'])}."
            )
        else:
            line += "."
        lines += [line, ""]

    lines += [
        f"_Generated {generated or now_iso()} by modelbench {__version__}. "
        f"Suite{'s' if len(suite_ids) > 1 else ''}: "
        + ", ".join(f"`{s}`" for s in sorted(suite_ids))
        + "._",
        "",
        "## Headline",
        "",
        "Scores are means over tasks (each task weighs the same), then over samples. "
        "`first` is the answer before any feedback; `final` allows one repair turn in which "
        "only failing assertion messages are returned.",
        "",
        "| metric | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]

    rows: list[tuple[str, list[str]]] = [
        ("records / expected", [f"{m['records']} / {m['expected']}" for m in metrics]),
        ("mean task score, first", [pct(m["first_score"]) for m in metrics]),
        ("mean task score, final", [pct(m["final_score"]) for m in metrics]),
        (
            "first-attempt assertions",
            [f"{m['assertions_passed']}/{m['assertions_total']} ({pct(m['assertion_rate'])})" for m in metrics],
        ),
        ("fully solved, first", [pct(m["solved_first"]) for m in metrics]),
        ("fully solved, final", [pct(m["solved_final"]) for m in metrics]),
        (
            "repair turns / improved / solved",
            [f"{m['repairs']} / {m['improved']} / {m['repaired_solved']}" for m in metrics],
        ),
        ("median call wall", [f"{m['median_call_s']:.1f}s" for m in metrics]),
        ("p90 call wall", [f"{m['p90_call_s']:.1f}s" for m in metrics]),
        ("median output tokens / call", [int_fmt(m["median_tokens"]) for m in metrics]),
        ("completion tokens, total", [f"{m['total_tokens']:,}" for m in metrics]),
        ("tokens per solved task", [
            int_fmt(m["total_tokens"] / solved) if (solved := sum(1 for r in run.records if r.get("final_solved"))) else MISSING
            for m, run in zip(metrics, runs)
        ]),
        ("wall clock, total", [f"{m['wall_s'] / 60:.1f} min" for m in metrics]),
        ("median decode speed", [f"{m['median_tps']:.1f} tok/s" if m["median_tps"] else MISSING for m in metrics]),
        ("median TTFT", [f"{m['median_ttft']:.2f}s" if m["median_ttft"] else MISSING for m in metrics]),
        ("answers cut by token cap", [str(m["truncated"]) for m in metrics]),
    ]
    for label, cells in rows:
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    # -- per task -------------------------------------------------------- #
    per_task = [per_task_metrics(run) for run in runs]
    all_tasks = sorted({task for metrics_by_task in per_task for task in metrics_by_task})
    lines += ["", "## Per task", ""]
    if len(runs) == 2:
        lines += [
            "| task | category | " + " | ".join(labels) + " | Δ (pp) | winner |",
            "|---|---|" + "---|" * len(labels) + "---|---|",
        ]
        for task in all_tasks:
            cells, values = [], []
            for m in per_task:
                entry = m.get(task)
                values.append(entry["first"] if entry else None)
                cells.append(pct(entry["first"]) if entry else MISSING)
            delta = ""
            winner = ""
            if values[0] is not None and values[1] is not None:
                d = (values[0] - values[1]) * 100
                delta = _signed_pp(d)
                winner = "tie" if abs(d) < 0.05 else (labels[0] if d > 0 else labels[1])
            category = next((m[task]["category"] for m in per_task if task in m), "")
            lines.append(f"| {task} | {category} | " + " | ".join(cells) + f" | {delta} | {winner} |")
        if pairs:
            pair = pairs[0]
            lines += [
                "",
                f"Task wins: **{pair.a} {pair.wins_a}**, **{pair.b} {pair.wins_b}**, {pair.ties} ties. "
                f"Mean per-task delta: {_signed_pp(pair.mean_delta_pp)} pp.",
            ]
    else:
        lines += ["| task | category | " + " | ".join(labels) + " | best |", "|---|---|" + "---|" * len(labels) + "---|"]
        for task in all_tasks:
            cells, values = [], []
            for m in per_task:
                entry = m.get(task)
                values.append(entry["first"] if entry else None)
                cells.append(pct(entry["first"]) if entry else MISSING)
            best_value = max((v for v in values if v is not None), default=None)
            best = MISSING
            if best_value is not None:
                best = ", ".join(labels[i] for i, v in enumerate(values) if v is not None and abs(v - best_value) < 1e-9)
            category = next((m[task]["category"] for m in per_task if task in m), "")
            lines.append(f"| {task} | {category} | " + " | ".join(cells) + f" | {best} |")

    # -- per category ---------------------------------------------------- #
    categories = sorted({c for run in runs for c in per_category_metrics(run)})
    lines += ["", "## Per category", ""]
    lines += ["| category | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    cat_metrics = [per_category_metrics(run) for run in runs]
    for category in categories:
        cells = [pct(m[category]["first"]) if category in m else MISSING for m in cat_metrics]
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    # -- provenance ------------------------------------------------------ #
    lines += ["", "## Provenance", ""]
    lines += [
        "| run | endpoint | served id | samples | records | suite | digest |",
        "|---|---|---|---|---|---|---|",
    ]
    for run, m in zip(runs, metrics):
        target = run.header.get("target") or {}
        served = target.get("served_id") or run.records[0].get("served_id") or target.get("model") or ""
        base_url = target.get("base_url") or ""
        digest = (run.header.get("suite") or {}).get("digest") or run.records[0].get("suite_digest") or ""
        lines.append(
            f"| {run.label} | {base_url} | {served} | {m['samples']} | {m['records']}/{m['expected']} | "
            f"`{run.suite_id}` | `{digest[:12]}` |"
        )

    # -- integrity ------------------------------------------------------- #
    lines += ["", "## Integrity", ""]
    any_issue = False
    for run, m in zip(runs, metrics):
        if m["missing"]:
            any_issue = True
            preview = ", ".join(f"{x['task']} s{x['sample']}" for x in m["missing"][:6])
            more = f" (+{len(m['missing']) - 6} more)" if len(m["missing"]) > 6 else ""
            lines.append(f"- **{run.label}**: {len(m['missing'])} missing record(s): {preview}{more}")
        if m["duplicates"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {len(m['duplicates'])} duplicated task/sample record(s)")
        if m["truncated"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {m['truncated']} first answer(s) hit the token cap")
        if m["no_result"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {m['no_result']} grader run(s) produced no `RESULT` line")
        raw = m["sources"].get("raw", 0)
        unclosed = m["sources"].get("fence-unclosed", 0)
        if raw:
            any_issue = True
            lines.append(f"- **{run.label}**: {raw} answer(s) had no code fence and were graded verbatim")
        if unclosed:
            lines.append(f"- **{run.label}**: {unclosed} answer(s) ended inside an unclosed fence (salvaged)")
        if m["errors"]:
            lines.append(f"- **{run.label}**: {m['errors']} record(s) carry a run error")
        if not m["missing"] and not m["duplicates"]:
            lines.append(
                f"- **{run.label}**: complete — {m['records']} of {m['expected']} expected records, no duplicates"
            )
    if not any_issue and runs:
        lines.append("")
        lines.append("No integrity problems detected.")

    if notes:
        lines += ["", "## Notes", "", notes.strip()]

    lines += [
        "",
        "## Reproducing this report",
        "",
        "```bash",
        "# one target from your modelbench.toml",
    ]
    for run in runs:
        target = (run.header.get("target") or {}).get("name") or run.label
        lines.append(f"modelbench run --target {target} --suite {run.suite_id} --samples {run.samples} --out runs/{target}")
    lines += [
        "modelbench report runs/" + " runs/".join(
            ((run.header.get("target") or {}).get("name") or run.label) for run in runs
        ),
        "```",
        "",
        "Exact prompts, raw model output and extracted solutions for every record are stored "
        "next to `results.jsonl` in each run directory (`s<N>/raw/`, `s<N>/sol/`).",
        "",
    ]
    return "\n".join(lines)


def render_json(runs: Sequence[Run], title: str | None = None) -> dict:
    payload = {
        "generated_at": now_iso(),
        "modelbench": __version__,
        "title": title or " vs ".join(run.label for run in runs),
        "runs": [],
        "pairwise": [],
    }
    for run in runs:
        payload["runs"].append(
            {
                "label": run.label,
                "path": str(run.path),
                "target": run.header.get("target") or {},
                "served_id": run.records[0].get("served_id"),
                "suite": run.header.get("suite") or {"id": run.suite_id},
                "metrics": run_metrics(run),
                "tasks": per_task_metrics(run),
                "categories": per_category_metrics(run),
            }
        )
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            pair = pairwise(runs[i], runs[j])
            payload["pairwise"].append(
                {
                    "a": pair.a,
                    "b": pair.b,
                    "wins_a": pair.wins_a,
                    "wins_b": pair.wins_b,
                    "ties": pair.ties,
                    "mean_delta_pp": round(pair.mean_delta_pp, 2),
                    "tasks": pair.rows,
                }
            )
    return payload


def render_console(runs: Sequence[Run]) -> str:
    metrics = [run_metrics(run) for run in runs]
    rows = []
    for run, m in zip(runs, metrics):
        rows.append(
            [
                run.label,
                pct(m["first_score"]),
                pct(m["final_score"]),
                pct(m["solved_first"]),
                f"{m['records']}/{m['expected']}",
                f"{m['median_call_s']:.1f}s",
                f"{m['median_tps']:.1f}" if m["median_tps"] else MISSING,
                f"{m['total_tokens']:,}",
            ]
        )
    table = column_table(
        ["run", "first", "final", "solved", "records", "med call", "tok/s", "tokens"],
        rows,
        align=["l", "r", "r", "r", "r", "r", "r", "r"],
    )
    lines = [table]
    if len(runs) == 2:
        pair = pairwise(runs[0], runs[1])
        lines.append(
            f"\ntask wins: {pair.a} {pair.wins_a}, {pair.b} {pair.wins_b}, ties {pair.ties} "
            f"(mean delta {_signed_pp(pair.mean_delta_pp)} pp)"
        )
    return "\n".join(lines)


def write_reports(
    runs: Sequence[Run],
    out_dir: str | Path,
    title: str | None = None,
    notes: str | None = None,
) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(runs, title=title, notes=notes)
    md_path = out / "REPORT.md"
    md_path.write_text(markdown, encoding="utf-8")
    json_path = out / "summary.json"
    write_json(json_path, render_json(runs, title=title))
    return md_path, json_path


def discover_runs(root: str | Path) -> list[Path]:
    """Every run directory below *root* (a directory holding run.json/results.jsonl)."""
    root = Path(root).expanduser()
    if (root / "results.jsonl").is_file():
        return [root]
    found = []
    for candidate in sorted(root.iterdir()) if root.is_dir() else []:
        if not candidate.is_dir():
            continue
        if (candidate / "results.jsonl").is_file():
            found.append(candidate)
    return found


def dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)
