from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import solution_arg  # noqa: E402

path = solution_arg()

BUGS = [
    ("accounts_mutable_default", "accounts.py", 22, 24),
    ("pricing_is_comparison", "pricing.py", 9, 9),
    ("pricing_tax_on_gross", "pricing.py", 13, 15),
    ("files_unclosed_handle", "files.py", 4, 6),
    ("cache_clear_all", "cache.py", 10, 11),
    ("retry_swallows_error", "retry.py", 6, 8),
    ("lock_unused", "lock.py", 8, 10),
]
TOTAL = 2 * len(BUGS)

try:
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("findings", [])
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    findings = []
    for item in data:
        if not isinstance(item, dict):
            continue
        fname = str(item.get("file", "")).replace("\\", "/").split("/")[-1]
        try:
            line = int(item.get("line"))
        except (TypeError, ValueError):
            continue
        findings.append((fname, line))
except Exception as exc:  # noqa: BLE001
    print(f"FAIL invalid JSON: {type(exc).__name__}: {exc}")
    print(f"RESULT 0/{TOTAL}")
    sys.exit(0)


def matches(fname, line, bug):
    _name, want_file, lo, hi = bug
    return fname == want_file and lo <= line <= hi


matched = 0
for bug in BUGS:
    hit = any(matches(f, ln, bug) for f, ln in findings)
    if hit:
        matched += 1
    else:
        print(f"FAIL missing {bug[0]} ({bug[1]}:{bug[2]}-{bug[3]})")

false_positives = [(f, ln) for f, ln in findings if not any(matches(f, ln, bug) for bug in BUGS)]
for f, ln in false_positives:
    print(f"FAIL false-positive {f}:{ln}")

precision_credit = max(0, matched - len(false_positives))
passed = matched + precision_credit
print(f"INFO findings={len(findings)} matched={matched} false_positives={len(false_positives)}")
print(f"RESULT {passed}/{TOTAL}")
