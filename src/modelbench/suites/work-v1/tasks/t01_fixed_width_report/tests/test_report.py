#!/usr/bin/env python3
"""Grade the fixed-width report by comparing columns, not just the whole blob.

A line that differs is reported as "first difference at character N (COLUMN)",
so the feedback says which rule was broken instead of handing back the answer.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

EXPECTED = """REGION   PRODUCT           UNITS      REVENUE   SHARE
-----------------------------------------------------
North    Widget            1,200   $14,500.50   28.6%
South    Widget              980   $11,899.99   23.4%
East     Widget              760    $8,999.95   17.7%
West     Widget              600    $7,250.00   14.3%
West     Gadget              410    $3,100.50    6.1%
North    Gadget              340    $2,250.00    4.4%
East     Industrial Brac…     88    $1,299.00    2.6%
Central  Doohickey           220      $999.99    2.0%
South    Doohickey           150      $450.00    0.9%
TOTAL                      4,748   $50,749.93  100.0%"""

COLUMNS = [
    ("REGION", 0, 8),
    ("PRODUCT", 9, 16),
    ("UNITS", 26, 6),
    ("REVENUE", 33, 12),
    ("SHARE", 46, 7),
]

ROW_NAMES = [
    "row 1 (largest revenue)",
    "row 2",
    "row 3",
    "row 4",
    "row 5",
    "row 6",
    "row 7 (truncated product)",
    "row 8",
    "row 9 (smallest revenue)",
]

C = Checks()
path = solution_arg()
try:
    raw = open(path, encoding="utf-8", errors="replace").read()
except OSError as exc:
    C.check("solution file is readable", lambda: (_ for _ in ()).throw(exc))
    C.report()

text = raw.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
lines = text.split("\n")


def compare(name: str, index: int) -> None:
    """Fail with the first differing character and the column it belongs to."""

    def run() -> None:
        if index >= len(lines):
            raise AssertionError(f"line {index + 1} is missing")
        got, want = lines[index], EXPECTED.split("\n")[index]
        if got == want:
            return
        pos = next(
            (i for i, (a, b) in enumerate(zip(got, want)) if a != b),
            min(len(got), len(want)),
        )
        column = next((n for n, start, width in COLUMNS if start <= pos < start + width), "line width")
        raise AssertionError(
            f"first difference at character {pos + 1} ({column}): "
            f"line has {len(got)} characters, expected {len(want)}"
        )

    C.check(name, run)


C.eq("report has exactly twelve lines", len(lines), 12)
compare("header row", 0)
compare("separator row", 1)
for offset, label in enumerate(ROW_NAMES):
    compare(label, 2 + offset)
compare("total row", 11)
C.false(
    "no line ends with a space",
    any(line != line.rstrip(" ") for line in lines),
)
C.true(
    "every line is 53 characters wide",
    all(len(line) == 53 for line in lines),
)

C.report()
