#!/usr/bin/env python3
"""Run the submitted query against two datasets, so a hardcoded answer fails."""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

SCHEMA = """
CREATE TABLE users  (id INTEGER PRIMARY KEY, signup_date TEXT NOT NULL);
CREATE TABLE events (user_id INTEGER NOT NULL, event_date TEXT NOT NULL, kind TEXT NOT NULL);
"""

DATASETS = {
    "A": {
        "users": [
            (1, "2025-01-05"), (2, "2025-01-20"), (3, "2025-01-31"),
            (4, "2025-02-10"), (5, "2025-02-28"), (6, "2025-03-15"),
        ],
        "events": [
            (1, "2025-02-01", "active"), (1, "2025-03-03", "active"), (1, "2025-04-10", "active"),
            (2, "2025-01-15", "active"), (2, "2025-05-01", "active"),
            (3, "2025-02-28", "active"), (3, "2025-02-27", "passive"), (3, "2025-04-01", "active"),
            (4, "2025-03-01", "active"), (4, "2025-04-05", "active"), (4, "2025-05-06", "active"),
            (5, "2025-03-10", "passive"), (5, "2025-05-10", "active"), (5, "2025-06-01", "active"),
            (6, "2025-04-02", "active"), (6, "2025-06-15", "active"),
        ],
    },
    "B": {
        "users": [(1, "2024-11-03"), (2, "2024-12-15"), (3, "2024-12-31")],
        "events": [
            (1, "2024-11-20", "active"), (1, "2024-12-01", "active"),
            (1, "2025-01-04", "active"), (1, "2025-02-02", "active"),
            (2, "2024-12-20", "active"), (2, "2025-01-01", "passive"), (2, "2025-03-01", "active"),
            (3, "2025-01-31", "active"),
        ],
    },
}


def build(spec: dict) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO users VALUES (?, ?)", spec["users"])
    con.executemany("INSERT INTO events VALUES (?, ?, ?)", spec["events"])
    return con


def expected(spec: dict) -> list[tuple]:
    members: dict[str, list[int]] = {}
    for uid, signup in spec["users"]:
        members.setdefault(signup[:7], []).append(uid)
    rows = []
    for cohort in sorted(members):
        ids = members[cohort]
        sy, sm = int(cohort[:4]), int(cohort[5:7])
        hits = [0, 0, 0]
        for uid in ids:
            offsets = set()
            for event_uid, event_date, kind in spec["events"]:
                if event_uid != uid or kind != "active":
                    continue
                ey, em = int(event_date[:4]), int(event_date[5:7])
                offset = (ey - sy) * 12 + (em - sm)
                if 1 <= offset <= 3:
                    offsets.add(offset)
            for index in range(3):
                if index + 1 in offsets:
                    hits[index] += 1
        total = len(ids)
        rows.append((cohort, total, *[f"{100.0 * hit / total:.1f}" for hit in hits]))
    return rows


def norm(value) -> str:
    return f"{value:.1f}" if isinstance(value, float) else str(value)


C = Checks()
path = solution_arg()
try:
    query = open(path, encoding="utf-8", errors="replace").read()
except OSError as exc:
    C.check("solution file is readable", lambda: (_ for _ in ()).throw(exc))
    C.report()

results: dict[str, list[tuple]] = {}
errors: dict[str, str] = {}
for name, spec in DATASETS.items():
    try:
        con = build(spec)
        cursor = con.execute(query)
        results[name] = cursor.fetchall()
        columns = [description[0].lower() for description in cursor.description or []]
        if name == "A":
            C.eq("query runs and returns five columns", len(columns), 5)
            C.eq("column names", columns, ["cohort", "users", "m1", "m2", "m3"])
    except Exception as exc:  # noqa: BLE001 - a broken query fails checks
        errors[name] = f"{type(exc).__name__}: {exc}"

if errors:
    C.check("query runs on dataset A", lambda: (_ for _ in ()).throw(AssertionError(errors.get("A", "not run"))))
    C.check("query runs on dataset B", lambda: (_ for _ in ()).throw(AssertionError(errors.get("B", "not run"))))
    C.report()

rows_a = results["A"]
rows_b = results["B"]
want_a = expected(DATASETS["A"])
want_b = expected(DATASETS["B"])


def column_check(name: str, rows: list[tuple], want: list[tuple], index: int) -> None:
    def run() -> None:
        got = [norm(row[index]) for row in rows]
        expected_column = [str(row[index]) for row in want]
        if got != expected_column:
            raise AssertionError(f"got {got} != want {expected_column}")

    C.check(name, run)


C.eq("dataset A: row count", len(rows_a), 3)
column_check("dataset A: cohorts", rows_a, want_a, 0)
column_check("dataset A: users", rows_a, want_a, 1)
column_check("dataset A: m1", rows_a, want_a, 2)
column_check("dataset A: m2", rows_a, want_a, 3)
column_check("dataset A: m3", rows_a, want_a, 4)
C.eq("dataset B: row count", len(rows_b), 2)
column_check("dataset B: cohorts", rows_b, want_b, 0)
column_check("dataset B: users", rows_b, want_b, 1)
column_check("dataset B: m1", rows_b, want_b, 2)
column_check("dataset B: m2", rows_b, want_b, 3)
column_check("dataset B: m3", rows_b, want_b, 4)

C.report()
