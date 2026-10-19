#!/usr/bin/env python3
"""Grade the memo extraction: shape, owners, dates, amounts and the exact quotes."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

EXPECTED = [
    ("Priya", "2025-11-14", None, "Priya will send the revised pricing sheet to the sales team by 14 November."),
    ("Marcus", "2025-11-21", 4800, "Marcus committed to booking the Berlin venue by Friday 21 November, with a budget of $4,800."),
    ("Legal", "2025-11-30", None, "Legal must return the data-processing addendum before the end of November."),
    ("Ana", "2025-12-01", None, "The support rotation moves to Ana on 1 December."),
    ("Tom", "2025-12-05", None, "Tom will draft the incident review by 5 December and circulate it to the board."),
    ("Finance", "2025-12-12", None, "Finance will reconcile the Q3 rebates by 12 December."),
    ("Elena", "2026-01-31", 12500, "Elena is to renew the SOC 2 certificate by 31 January 2026; the renewal quote is $12,500."),
]
KEYS = {"owner", "due", "amount_usd", "source"}

C = Checks()
path = solution_arg()
records: list = []
parse_error: str | None = None
try:
    raw = open(path, encoding="utf-8", errors="replace").read()
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        records = parsed
    else:
        parse_error = f"top level is {type(parsed).__name__}, want an array"
except Exception as exc:  # noqa: BLE001
    parse_error = f"{type(exc).__name__}: {exc}"

C.check(
    "answer is a JSON array",
    lambda: (_ for _ in ()).throw(AssertionError(parse_error)) if parse_error else None,
)


def check(name: str, fn) -> None:
    def run() -> None:
        if parse_error:
            raise AssertionError(f"cannot read the answer: {parse_error}")
        fn()

    C.check(name, run)


check("exactly seven records", lambda: (_ for _ in ()).throw(
    AssertionError(f"got {len(records)} records")
) if len(records) != 7 else None)


def keys_ok() -> None:
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != KEYS:
            raise AssertionError(f"record {index + 1} has keys {sorted(record) if isinstance(record, dict) else type(record)}")


check("every record has exactly the four keys", keys_ok)
check(
    "owners",
    lambda: (_ for _ in ()).throw(
        AssertionError(f"got {[r.get('owner') for r in records]}")
    ) if [r.get("owner") for r in records] != [row[0] for row in EXPECTED] else None,
)
check(
    "due dates, sorted",
    lambda: (_ for _ in ()).throw(
        AssertionError(f"got {[r.get('due') for r in records]}")
    ) if [r.get("due") for r in records] != [row[1] for row in EXPECTED] else None,
)


def amounts() -> None:
    got = {record.get("owner"): record.get("amount_usd") for record in records}
    want = {row[0]: row[2] for row in EXPECTED}
    if got != want:
        raise AssertionError(f"got {got} != want {want}")


def iso() -> None:
    for record in records:
        due = record.get("due")
        if not isinstance(due, str) or len(due) != 10 or due[4] != "-" or due[7] != "-":
            raise AssertionError(f"{due!r} is not YYYY-MM-DD")
        if record.get("amount_usd") is not None and not isinstance(record.get("amount_usd"), int):
            raise AssertionError(f"{record.get('amount_usd')!r} is not a whole number")


def excluded() -> None:
    joined = " ".join(str(record.get("source", "")).lower() for record in records)
    for word in ("churn", "dashboard", "lease"):
        if word in joined:
            raise AssertionError(f"an item about {word!r} is not a commitment")


def duplicates() -> None:
    seen = [record.get("source") for record in records]
    if len(set(seen)) != len(seen):
        raise AssertionError("the repeated sentence produced more than one record")


check("amounts", amounts)
check("dates are ISO and amounts are whole numbers", iso)
sources_by_owner = {row[0]: row[3] for row in EXPECTED}
for owner in [row[0] for row in EXPECTED]:
    def one(owner: str = owner) -> None:
        got = next((record.get("source") for record in records if record.get("owner") == owner), None)
        if got != sources_by_owner[owner]:
            raise AssertionError(f"source for {owner} is not the verbatim sentence")

    check(f"source: {owner}", one)

check("no non-commitment items", excluded)
check("no duplicate records", duplicates)

C.report()
