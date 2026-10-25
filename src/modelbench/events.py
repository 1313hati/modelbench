"""A structured, append-only event log for one run.

``results.jsonl`` answers "what did each task score". It cannot answer "what is
happening right now": a record only appears once a task is finished and graded,
so a run of twelve tasks with a 4K-token cap spends most of its wall clock
invisible. The TUI, and any external monitor, need the other half — a line at
the moment an attempt starts, a line when it ends, a line when a sample is
skipped or a task dies.

Events are flat JSON lines carrying a sequence number, so a reader can tail the
file without re-parsing it, and a truncated last line costs one event rather
than the file. They are a *view* of a run, never the source of truth: every
report is built from ``results.jsonl``, and deleting ``events.jsonl`` costs no
measurement. That asymmetry is deliberate — the log is allowed to miss a line,
the results file is not.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from .util import now_iso, read_jsonl

EVENT_VERSION = 1
EVENT_FILE = "events.jsonl"

#: Kinds this package emits. Readers must tolerate unknown kinds.
KINDS = (
    "run_started",
    "warmup_started",
    "attempt_started",
    "attempt_finished",
    "attempt_failed",
    "sample_skipped",
    "warning",
    "run_finished",
)


class EventLog:
    """Thread-safe writer for ``events.jsonl``.

    The runner may have several pair-workers in flight, so ``emit`` serialises
    on a lock and flushes every line: a monitor tailing the file must see an
    event within one poll interval, not when a buffer happens to fill.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._fh = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 - owned by this object

    def emit(self, kind: str, **fields: Any) -> dict:
        """Append one event and return the dict that was written."""
        with self._lock:
            self._seq += 1
            # Envelope last: a caller field called "seq" or "t" must not be able
            # to corrupt the one structure every reader keys on.
            event = {
                **fields,
                "v": EVENT_VERSION,
                "seq": self._seq,
                "kind": kind,
                "at": now_iso(),
                "t": round(time.time(), 3),
            }
            self._fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._fh.flush()
            return event

    def close(self) -> None:
        with self._lock:
            if not self._fh.closed:
                self._fh.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_events(path: str | Path) -> list[dict]:
    """Every event in a log; an absent file is an empty log, not an error."""
    return [event for event in read_jsonl(Path(path)) if isinstance(event, dict)]


def iter_new(path: str | Path, offset: int = 0) -> Iterator[tuple[dict, int]]:
    """Yield ``(event, new_offset)`` for each line past ``offset``.

    ``offset`` is a byte position. The caller keeps the last offset it saw, so
    a monitor reads each line once. A partially written final line is left for
    the next call: its bytes stay in the offset so it is re-read whole.
    """
    file = Path(path)
    try:
        size = file.stat().st_size
    except FileNotFoundError:
        return
    if size < offset:
        offset = 0  # the file was replaced or truncated; start again
    if size == offset:
        return
    with open(file, "rb") as fh:
        fh.seek(offset)
        while True:
            start = fh.tell()
            line = fh.readline()
            if not line:
                return
            if not line.endswith(b"\n"):
                # Half-written line: do not consume it, and do not parse it.
                fh.seek(start)
                return
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event, fh.tell()
