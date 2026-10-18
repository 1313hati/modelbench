"""Small shared helpers: hashing, time, statistics, text formatting."""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


# --------------------------------------------------------------------------- #
# time
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    """Local timestamp with seconds precision (matches bench records)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def human_duration(seconds: float) -> str:
    seconds = float(seconds or 0)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {rest:04.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes:02d}m"


# --------------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------------- #
def iter_files(root: Path) -> Iterable[Path]:
    """Yield regular files below *root* in a stable order."""
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.startswith("."))
        for name in sorted(names):
            if name.endswith((".pyc", ".pyo")) or name.startswith("."):
                continue
            yield Path(base) / name


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_dir(root: Path) -> str:
    """Content hash of a directory tree.

    Stable across machines: only relative paths and file bytes are hashed, so a
    suite digest can be compared between two people running the same tasks.
    """
    digest = hashlib.sha256()
    root = Path(root)
    for path in sorted(iter_files(root)):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def short_hash(value: str, length: int = 12) -> str:
    return (value or "")[:length]


# --------------------------------------------------------------------------- #
# json
# --------------------------------------------------------------------------- #
def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return records


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def p90(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))
    return ordered[idx]


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #
def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{100 * value:.{digits}f}%"


def num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def int_fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}"


def tail(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return "…(truncated)…\n" + text[-limit:]


def column_table(headers: Sequence[str], rows: Sequence[Sequence[str]], align: Sequence[str] | None = None) -> str:
    """Plain-text table that renders in any terminal."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    align = align or ["l"] * len(headers)

    def render(cells: Sequence[str]) -> str:
        parts = []
        for cell, width, a in zip(cells, widths, align):
            text = str(cell)
            parts.append(text.ljust(width) if a == "l" else text.rjust(width))
        return "  ".join(parts).rstrip()

    lines = [render(headers), "  ".join("-" * w for w in widths)]
    lines.extend(render([str(c) for c in row]) for row in rows)
    return "\n".join(lines)


def csv_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


def safe_rel(path: str) -> str | None:
    """Normalise a model-supplied relative path; reject escapes."""
    rel = (path or "").strip().strip("`'\"")
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.startswith("/") or ":" in rel.split("/")[0]:
        return None
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)
