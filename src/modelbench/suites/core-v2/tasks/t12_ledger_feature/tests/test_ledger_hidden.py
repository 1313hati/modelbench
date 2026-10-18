from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
sys.path.insert(0, solution_arg())

try:
    from ledger import Entry, Posting, account_balances, allocate, trial_balance
except Exception as exc:  # noqa: BLE001
    C.check("ledger imports", lambda: (_ for _ in ()).throw(exc))
    C.report()


def reference_allocate(total, weights):
    s = sum(weights)
    raw = [total * w for w in weights]
    shares = [x // s for x in raw]
    rem = total - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] % s), i))
    for i in order[:rem]:
        shares[i] += 1
    return shares


C.eq("largest remainder", allocate(10, [6, 4, 1]), [5, 4, 1])
C.eq("uneven weights", allocate(100, [1, 2, 3]), [17, 33, 50])
C.eq("equal split", allocate(5, [1, 1, 1]), [2, 2, 1])
C.eq("one unit tie", allocate(1, [1, 1, 1]), [1, 0, 0])
C.eq("seven over three", allocate(7, [2, 2, 2]), [3, 2, 2])
C.eq("zero total", allocate(0, [3, 7]), [0, 0])
C.eq("large total", allocate(10**9, [3, 5, 7]), reference_allocate(10**9, [3, 5, 7]))


def invariants():
    rng = random.Random(19)
    for _ in range(150):
        n = rng.randint(1, 8)
        weights = [rng.randint(1, 50) for _ in range(n)]
        total = rng.randint(0, 10000)
        got = allocate(total, weights)
        want = reference_allocate(total, weights)
        if got != want:
            raise AssertionError(f"total={total} weights={weights}: {got} != {want}")


C.check("150 random allocations", invariants)


def no_mutation():
    weights = [4, 5, 6]
    allocate(17, weights)
    assert weights == [4, 5, 6]


C.check("weights not mutated", no_mutation)

C.raises("negative total", ValueError, lambda: allocate(-1, [1]))
C.raises("float total", ValueError, lambda: allocate(1.5, [1]))
C.raises("empty weights", ValueError, lambda: allocate(10, []))
C.raises("zero weight", ValueError, lambda: allocate(10, [1, 0]))
C.raises("negative weight", ValueError, lambda: allocate(10, [1, -2]))
C.raises("float weight", ValueError, lambda: allocate(10, [1, 2.0]))
C.raises("weights not list", ValueError, lambda: allocate(10, "12"))

E = Entry
P = Posting

entries = [
    E("e1", (P("1000", 10000), P("4000", -10000))),
    E("e2", (P("1000", -2500), P("5000", 2500))),
    E("e3", (P("1000", 1000), P("2000", -1000))),
]
C.eq(
    "natural balances",
    account_balances(entries),
    {"1000": 8500, "4000": 10000, "5000": 2500, "2000": 1000},
)
C.eq("account_balances empty", account_balances([]), {})
C.eq(
    "zero balance account included",
    account_balances([E("z", (P("1000", 100), P("1000", -100)))]),
    {"1000": 0},
)
C.eq(
    "equity and revenue credit-positive",
    account_balances([
        E("e4", (P("1000", 700), P("3000", -700))),
        E("e5", (P("1100", 300), P("4000", -300))),
    ]),
    {"1000": 700, "3000": 700, "1100": 300, "4000": 300},
)
C.raises(
    "unknown account rejected",
    ValueError,
    lambda: account_balances([E("bad", (P("9999", 5), P("1000", -5)))]),
)

C.eq("trial balance empty", trial_balance([]), [])
C.eq(
    "trial balance sorted and non-zero",
    trial_balance([
        E("e1", (P("1000", 500), P("4000", -500))),
        E("e2", (P("5000", 200), P("1000", -200))),
    ]),
    [
        ("1000", "Cash", 300),
        ("4000", "Revenue", 500),
        ("5000", "Expenses", 200),
    ],
)
C.eq(
    "trial balance drops zero",
    trial_balance([E("z", (P("1000", 100), P("1000", -100)))]),
    [],
)


def generator_input():
    gen = (e for e in entries)
    assert account_balances(gen)["1000"] == 8500


C.check("accepts an iterable of entries", generator_input)

C.report()
