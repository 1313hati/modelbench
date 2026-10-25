"""A live dashboard for a run, in the terminal, without dependencies.

Why a TUI at all: a benchmark of twelve tasks at a 4K cap takes twenty minutes
to an hour, and the plain progress lines scroll away. The question a person
actually has while waiting is not "what did task 3 score" but "is it moving,
how fast, and will it finish before I go to bed". Those are three different
looks at the same file, so this module renders them as one screen.

The design keeps the interesting part testable: :func:`render_frame` is a pure
function from a :class:`TuiState` and a size to a list of lines, so the layout
can be asserted in a unit test at 40x12 and 200x60 without a terminal anywhere.
The curses loop below only pumps keys and draws those lines.

It reads three files and never writes: ``run.json`` (what the run claims to be),
``results.jsonl`` (what has finished) and ``events.jsonl`` (what is in flight).
A run directory that is still being created renders as "waiting", not as an
error — ``modelbench run --tui`` starts watching before the first record exists.
"""

from __future__ import annotations

import curses
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .util import human_duration, percentile, read_jsonl

#: A wide, curated block ramp. Every glyph is single-width in a monospace
#: terminal; the low block is the floor so a zero still draws something.
SPARK = "▁▂▃▄▅▆▇█"
SPARK_ASCII = ".:-=+*#@"

BAR_FULL, BAR_EMPTY = "█", "░"
BAR_FULL_ASCII, BAR_EMPTY_ASCII = "#", "-"

STYLES = ("title", "rule", "progress", "header", "row", "bad", "dim", "warn", "footer")


@dataclass
class Frame:
    """Lines plus one style name per line, so colour is a drawing concern."""

    lines: list[str]
    styles: list[str]

    def __iter__(self):
        return iter(self.lines)

    def __len__(self) -> int:
        return len(self.lines)

    def text(self) -> str:
        return "\n".join(self.lines)


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #
def _parse_iso(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass
class TuiState:
    """Everything the screen needs, recomputed from disk on demand."""

    path: Path
    header: dict = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    _results_size: int = -1
    _events_size: int = -1
    _header_mtime: float = -1.0
    loaded: bool = False

    # -- loading --------------------------------------------------------- #
    def refresh(self) -> "TuiState":
        run_json = self.path / "run.json"
        results = self.path / "results.jsonl"
        events = self.path / "events.jsonl"

        try:
            mtime = run_json.stat().st_mtime
        except OSError:
            mtime = -1.0
        if mtime != self._header_mtime or not self.loaded:
            if mtime >= 0:
                self.header = _read_json(run_json)
            self._header_mtime = mtime

        try:
            size = results.stat().st_size
        except OSError:
            size = -1
        if size != self._results_size:
            self.records = [r for r in read_jsonl(results) if isinstance(r, dict)] if size > 0 else []
            self._results_size = size

        try:
            esize = events.stat().st_size
        except OSError:
            esize = -1
        if esize != self._events_size:
            self.events = [e for e in read_jsonl(events) if isinstance(e, dict)] if esize > 0 else []
            self._events_size = esize

        self.loaded = bool(self.header) or bool(self.records) or bool(self.events)
        return self

    # -- shape ----------------------------------------------------------- #
    @property
    def status(self) -> str:
        status = str(self.header.get("status") or "")
        if status:
            return status
        if any(e.get("kind") == "run_finished" for e in self.events):
            return "finished"
        return "running" if self.loaded else "waiting"

    @property
    def suite(self) -> str:
        suite = (self.header.get("suite") or {}).get("id")
        if suite:
            version = (self.header.get("suite") or {}).get("version")
            return f"{suite} {version}".strip() if version else str(suite)
        started = next((e for e in self.events if e.get("kind") == "run_started"), None)
        return str((started or {}).get("suite") or "—")

    @property
    def target(self) -> str:
        name = (self.header.get("target") or {}).get("name")
        if name:
            return str(name)
        started = next((e for e in self.events if e.get("kind") == "run_started"), None)
        return str((started or {}).get("target") or self.path.name)

    @property
    def samples(self) -> int:
        if self.header.get("samples"):
            return max(1, int(self.header["samples"]))
        return max((int(r.get("sample") or 1) for r in self.records), default=1)

    @property
    def tasks(self) -> list[str]:
        declared = (self.header.get("suite") or {}).get("tasks") or []
        if declared:
            return [str(t) for t in declared]
        started = next((e for e in self.events if e.get("kind") == "run_started"), None)
        if started and started.get("tasks"):
            return [str(t) for t in started["tasks"]]
        seen: list[str] = []
        for record in self.records:
            task = str(record.get("task"))
            if task not in seen:
                seen.append(task)
        return seen

    @property
    def total_pairs(self) -> int:
        return max(1, len(self.tasks) * self.samples)

    @property
    def started_at(self) -> float | None:
        when = _parse_iso(self.header.get("started_at"))
        if when is not None:
            return when
        first = next((e for e in self.events if e.get("t")), None)
        return float(first["t"]) if first else None

    @property
    def finished_at(self) -> float | None:
        return _parse_iso(self.header.get("finished_at"))

    def elapsed(self, now: float | None = None) -> float:
        now = now or time.time()
        start = self.started_at
        if start is None:
            return 0.0
        end = self.finished_at or now
        return max(0.0, end - start)

    def eta(self, now: float | None = None) -> float | None:
        done = self.completed
        if self.status != "running" or done <= 0:
            return None
        elapsed = self.elapsed(now)
        if elapsed <= 0:
            return None
        per_pair = elapsed / done
        return max(0.0, per_pair * (self.total_pairs - done))

    # -- records --------------------------------------------------------- #
    @property
    def completed(self) -> int:
        return len({(str(r.get("task")), int(r.get("sample") or 1)) for r in self.records})

    def score_grid(self) -> dict[str, dict[int, float]]:
        grid: dict[str, dict[int, float]] = {}
        for record in self.records:
            task = str(record.get("task"))
            sample = int(record.get("sample") or 1)
            grid.setdefault(task, {})[sample] = float(record.get("final_score") or 0.0)
        return grid

    def in_flight(self, now: float | None = None) -> list[dict]:
        """Attempts that started and have not finished yet.

        Keyed by (task, sample, phase). A repair start implies the first phase
        ended, and the finishing event names its own phase, so a pair can hold
        at most one live attempt without any explicit "current" pointer.
        """
        live: dict[tuple[str, int, str], dict] = {}
        for event in self.events:
            kind = event.get("kind")
            key = (str(event.get("task")), int(event.get("sample") or 1), str(event.get("phase") or "first"))
            if kind == "attempt_started":
                live[key] = event
            elif kind in {"attempt_finished", "attempt_failed"}:
                live.pop(key, None)
        now = now or time.time()
        out = []
        for event in live.values():
            out.append({**event, "age_s": max(0.0, now - float(event.get("t") or now))})
        return sorted(out, key=lambda e: e["age_s"], reverse=True)

    def speeds(self) -> list[float]:
        return [
            float(r["first"]["tok_per_s"])
            for r in self.records
            if isinstance(r.get("first"), dict) and r["first"].get("tok_per_s")
        ]

    def protocol_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            first = record.get("first") or {}
            kind = str(first.get("protocol") or "ok")
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def errors(self) -> int:
        failed = sum(1 for e in self.events if e.get("kind") == "attempt_failed")
        return failed + int((self.header or {}).get("errors") or 0)

    def warnings(self) -> list[dict]:
        return [e for e in self.events if e.get("kind") == "warning"]

    def total_tokens(self) -> int:
        return sum(
            int((r.get("first") or {}).get("completion_tokens") or 0) for r in self.records
        )

    def snapshot(self, now: float | None = None) -> dict:
        """The same numbers the screen shows, for ``--json`` and for tests."""
        now = now or time.time()
        speeds = self.speeds()
        median = percentile(speeds, 0.5) if speeds else None
        return {
            "path": str(self.path),
            "status": self.status,
            "suite": self.suite,
            "target": self.target,
            "samples": self.samples,
            "tasks": len(self.tasks),
            "records": self.completed,
            "expected": self.total_pairs,
            "elapsed_s": round(self.elapsed(now), 1),
            "eta_s": round(self.eta(now), 1) if self.eta(now) is not None else None,
            "in_flight": [
                {"task": e.get("task"), "sample": e.get("sample"), "phase": e.get("phase"), "age_s": round(e["age_s"], 1)}
                for e in self.in_flight(now)
            ],
            "median_tok_per_s": round(median, 1) if median is not None else None,
            "completion_tokens": self.total_tokens(),
            "errors": self.errors(),
            "protocols": self.protocol_counts(),
            "warnings": len(self.warnings()),
        }


# --------------------------------------------------------------------------- #
# drawing helpers
# --------------------------------------------------------------------------- #
def _fit(text: str, width: int, ellipsis: str = "…") -> str:
    """Pad or truncate to exactly *width*, counting characters not bytes."""
    if width <= 0:
        return ""
    if len(text) > width:
        tail = ellipsis if width > len(ellipsis) else ""
        return text[: max(0, width - len(tail))] + tail
    return text + " " * (width - len(text))


def _bar(fraction: float, width: int, unicode: bool = True) -> str:
    fraction = min(1.0, max(0.0, fraction))
    filled = int(round(fraction * width))
    full = BAR_FULL if unicode else BAR_FULL_ASCII
    empty = BAR_EMPTY if unicode else BAR_EMPTY_ASCII
    return full * filled + empty * (width - filled)


def sparkline(values: Sequence[float], width: int, unicode: bool = True) -> str:
    """A block sparkline scaled to the observed range.

    A flat series draws its middle glyph rather than a full bar: reading "all
    values identical" as "all values maximal" is the classic sparkline lie.
    """
    alphabet = SPARK if unicode else SPARK_ASCII
    if not values or width <= 0:
        return ""
    trimmed = list(values)[-width:]
    lo, hi = min(trimmed), max(trimmed)
    if hi - lo < 1e-9:
        return alphabet[len(alphabet) // 2] * len(trimmed)
    span = hi - lo
    return "".join(alphabet[min(len(alphabet) - 1, int((v - lo) / span * (len(alphabet) - 1)))] for v in trimmed)


def _dur(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return human_duration(seconds)


def _run_label(path: Path) -> str:
    """The run's own name. A dashboard has no room for a full absolute path."""
    try:
        resolved = Path(path).resolve()
    except OSError:  # pragma: no cover - unreadable cwd
        return str(path)
    return resolved.name or str(resolved)


# --------------------------------------------------------------------------- #
# the frame
# --------------------------------------------------------------------------- #
def render_frame(
    state: TuiState,
    width: int = 100,
    height: int = 30,
    *,
    unicode: bool = True,
    now: float | None = None,
    paused: bool = False,
    notice: str | None = None,
) -> Frame:
    """Draw one screen. Pure: same state, same size, same output."""
    now = now or time.time()
    width = max(30, int(width))
    height = max(8, int(height))
    lines: list[str] = []
    styles: list[str] = []
    tags: list[str] = []
    dots = "…" if unicode else "..."

    def add(text: str, style: str = "row", tag: str = "core") -> None:
        lines.append(_fit(text, width, dots))
        styles.append(style)
        tags.append(tag)

    title = "modelbench"
    left_full = f" {title}  {state.suite} · {state.target}"
    left_short = f" {title}  {state.target}"
    status = state.status
    clock = _dur(state.elapsed(now))
    eta = state.eta(now)
    right = f"{status}  {clock}"
    if eta:
        right += f"  ETA {_dur(eta)}"
    if paused:
        right = "PAUSED  " + right
    # The clock and the status are the reason to look at this screen; the suite
    # name is not. So the left side yields first, not the right.
    padding = -1
    for left in (left_full, left_short, f" {title}"):
        padding = width - len(left) - len(right) - 1
        if padding >= 1:
            add(left + " " * padding + right + " ", "title")
            break
    else:
        add((" " + right).rjust(width), "title")

    add("─" * width if unicode else "-" * width, "rule")

    done, total = state.completed, state.total_pairs
    fraction = done / total if total else 0.0
    bar_width = max(6, min(40, width - 34))
    label = f" {int(fraction * 100):>3}%  {done}/{total} pairs"
    add(" " + _bar(fraction, bar_width, unicode) + label, "progress")

    tasks = state.tasks
    grid = state.score_grid()
    in_flight = state.in_flight(now)
    live_by_task = {(str(e.get("task")), int(e.get("sample") or 1)): e for e in in_flight}

    # Column plan: drop the least important columns first, so the task name —
    # the only column a human is actually scanning — survives a narrow window.
    show_speeds = width >= 56
    show_protocol = width >= 74
    sample_cols = max(1, min(state.samples, max(1, (width - 34) // 6)))
    fixed = 2 + sample_cols * 6 + 9
    if show_speeds:
        fixed += 8
    if show_protocol:
        fixed += 12
    name_width = max(10, min(30, width - fixed))

    header = "  task".ljust(name_width + 2)
    for index in range(1, sample_cols + 1):
        header += f"  s{index}".rjust(6)
    if show_speeds:
        header += "    t/s"
    header += f"  {'state':>7s}"
    if show_protocol:
        header += "  protocol"
    add(header, "header")

    overhead = 9  # title, rule, progress, header, blank, now, speed, errors, footer
    rows_available = max(1, height - overhead)
    visible = tasks[:rows_available]
    for task in visible:
        samples_done = grid.get(task, {})
        line = "  " + _fit(task, name_width, dots)
        for index in range(1, sample_cols + 1):
            if index in samples_done:
                line += f"{samples_done[index] * 100:5.0f}%"
            elif (task, index) in live_by_task:
                line += "    ·"
            else:
                line += "    -"
        style = "row"
        running = any(key[0] == task for key in live_by_task)
        if show_speeds:
            speeds = [
                float((r.get("first") or {}).get("tok_per_s") or 0.0)
                for r in state.records
                if str(r.get("task")) == task and (r.get("first") or {}).get("tok_per_s")
            ]
            rate = f"{percentile(speeds, 0.5):5.1f}" if speeds and percentile(speeds, 0.5) else "    ·"
            line += "  " + rate
        if samples_done and len(samples_done) >= state.samples:
            state_label = "done"
        elif samples_done:
            state_label = "partial" if not running else "running"
        elif running:
            state_label = "running"
        else:
            state_label = "pending"
        if state_label == "running":
            style = "warn"
        line += f"  {state_label:>7s}"
        if show_protocol:
            protocols = {
                str((r.get("first") or {}).get("protocol") or "ok")
                for r in state.records
                if str(r.get("task")) == task
            }
            odd = sorted(p for p in protocols if p != "ok")
            line += "  " + _fit(",".join(odd) if odd else "·", 11, dots)
        add(line, style)

    if len(tasks) > len(visible):
        add(f"  … {len(tasks) - len(visible)} more task(s)", "dim", tag="drop-more")
    add("", "dim")

    if in_flight:
        current = in_flight[0]
        phase = str(current.get("phase") or "first")
        add(
            f"  now  {current.get('task')} s{current.get('sample')} · {phase} · "
            f"{_dur(current['age_s'])}",
            "warn",
        )
    elif state.status == "running" and state.loaded:
        add("  now  waiting for the first attempt", "dim")
    elif state.status in {"finished", "failed", "interrupted"}:
        add(f"  run {state.status} · {done}/{total} pairs recorded", "dim")
    else:
        add("  waiting for the run directory", "dim")

    speeds = state.speeds()
    if speeds:
        median = percentile(speeds, 0.5)
        spark_width = max(4, min(24, width - 46))
        add(
            f"  {sparkline(speeds, spark_width, unicode)}  {median:.1f} tok/s median · "
            f"{state.total_tokens():,} tok",
            "dim",
            tag="drop-speed",
        )
    else:
        add("  no completed call yet", "dim", tag="drop-speed")

    protocols = state.protocol_counts()
    odd = {k: v for k, v in protocols.items() if k != "ok"}
    faults = ", ".join(f"{k} {v}" for k, v in sorted(odd.items()))
    warn = state.warnings()
    tail = f"  errors {state.errors()}"
    if faults:
        tail += f" · {faults}"
    if warn:
        tail += f" · {len(warn)} warning(s)"
    add(tail + f" · {_run_label(state.path)}", "bad" if (state.errors() or faults) else "dim", tag="drop-errors")

    footer = "  q quit · space pause · r refresh"
    if state.status in {"finished", "failed", "interrupted"}:
        footer = f"  run {state.status} · press q"

    # Exactly `height` lines: the curses driver clears and redraws by position,
    # and a test can assert the shape without knowing the content. When there
    # is not room for everything, the footer outlives the statistics — a screen
    # with no key hint is a screen the user has to guess at — and it owns the
    # last line, so it stays put while the table above it grows.
    while len(lines) > height - 1:
        for tag in ("drop-speed", "drop-errors", "drop-more"):
            index = next((i for i, marked in enumerate(tags) if marked == tag), None)
            if index is not None:
                del lines[index], styles[index], tags[index]
                break
        else:
            del lines[height - 1 :], styles[height - 1 :], tags[height - 1 :]
            break
    while len(lines) < height - 1:
        lines.append(" " * width)
        styles.append("dim")
        tags.append("core")
    lines.append(_fit(f"  {notice}" if notice else footer, width, dots))
    styles.append("warn" if notice else "footer")

    if not unicode:
        # One-width substitutions only: every line has already been measured,
        # so this cannot overflow the window it was fitted to.
        lines = [line.replace("·", "-") for line in lines]
    return Frame(lines[:height], styles[:height])


# --------------------------------------------------------------------------- #
# drivers
# --------------------------------------------------------------------------- #
def _term_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size()
    except OSError:  # pragma: no cover - unusual terminals
        return 100, 30
    return size.columns, size.lines


ANSI = {
    "title": "\033[1;37m",
    "rule": "\033[2;37m",
    "progress": "\033[36m",
    "header": "\033[2;37m",
    "row": "",
    "bad": "\033[31m",
    "dim": "\033[2;37m",
    "warn": "\033[33m",
    "footer": "\033[2;37m",
}
RESET = "\033[0m"


def render_text(
    state: TuiState,
    width: int = 100,
    height: int = 30,
    *,
    unicode: bool = True,
    colour: bool = False,
) -> str:
    frame = render_frame(state, width, height, unicode=unicode)
    if not colour:
        return frame.text()
    painted = []
    for line, style in zip(frame.lines, frame.styles):
        prefix = ANSI.get(style, "")
        painted.append(prefix + line + (RESET if prefix else ""))
    return "\n".join(painted)


def _draw(screen, frame: Frame) -> None:
    curses_attr = {
        "title": curses.A_BOLD,
        "rule": curses.A_DIM,
        "progress": curses.A_BOLD,
        "header": curses.A_DIM,
        "row": curses.A_NORMAL,
        "bad": curses.color_pair(1) if curses.has_colors() else curses.A_BOLD,
        "dim": curses.A_DIM,
        "warn": curses.color_pair(2) if curses.has_colors() else curses.A_BOLD,
        "footer": curses.A_DIM,
    }
    screen.erase()
    for index, (line, style) in enumerate(zip(frame.lines, frame.styles)):
        try:
            screen.addstr(index, 0, line, curses_attr.get(style, curses.A_NORMAL))
        except curses.error:  # writing the last cell of the last line
            pass
    screen.refresh()


def watch(
    path: str | Path,
    *,
    once: bool = False,
    follow: bool = False,
    interval: float = 0.25,
    unicode: bool | None = None,
    max_frames: int | None = None,
    lock_quit: bool = False,
    stop_when=None,
) -> int:
    """Show *path* live. Non-interactive output prints one frame and returns."""
    state = TuiState(Path(path)).refresh()
    if unicode is None:
        unicode = _supports_unicode()
    if once or not sys.stdout.isatty() or max_frames is not None:
        width, height = _term_size()
        frames = 0
        while True:
            state.refresh()
            print(render_text(state, width, height, unicode=unicode).rstrip())
            frames += 1
            if stop_when is not None and stop_when():
                return 0
            if not follow or (max_frames is not None and frames >= max_frames):
                return 0
            if state.status in {"finished", "failed", "interrupted"}:
                return 0
            time.sleep(interval)
    try:
        return curses.wrapper(_loop, state, follow, interval, bool(unicode), lock_quit, stop_when)
    except KeyboardInterrupt:
        return 130


def _supports_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _loop(
    screen,
    state: TuiState,
    follow: bool,
    interval: float,
    unicode: bool,
    lock_quit: bool = False,
    stop_when=None,
) -> int:
    curses.curs_set(0)
    screen.nodelay(True)
    screen.timeout(int(interval * 1000))
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_RED, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
        except curses.error:  # pragma: no cover - monochrome terminal
            pass
    paused = False
    notice: str | None = None
    finished_seen = state.status in {"finished", "failed", "interrupted"}
    while True:
        key = screen.getch()
        if key != -1:
            notice = None
        if key in (ord("q"), ord("Q"), 27):
            if lock_quit and state.status == "running":
                # Quitting here would end the process and take the run with it;
                # the honest thing is to say so instead of losing the pair.
                notice = "q is disabled while this run is writing · Ctrl-C stops the run"
            else:
                return 0
        if key in (ord("p"), ord("P"), ord(" ")):
            paused = not paused
        if key in (ord("r"), ord("R")):
            state._header_mtime = -1.0
            state._results_size = -1
            state._events_size = -1
        if not paused:
            state.refresh()
        height, width = screen.getmaxyx()
        _draw(
            screen,
            render_frame(state, width, height, unicode=unicode, paused=paused, notice=notice),
        )
        if stop_when is not None and stop_when():
            return 0
        if state.status in {"finished", "failed", "interrupted"}:
            if not follow:
                # One more second so the last numbers are readable, then leave
                # the terminal as we found it.
                time.sleep(1.0)
                return 0
            finished_seen = True
        elif finished_seen and follow:
            finished_seen = False
