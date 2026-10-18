from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

SCHEMA = """
CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE employees (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, dept_id INTEGER,
  salary INTEGER NOT NULL, hired_at TEXT NOT NULL
);
CREATE TABLE sales (
  id INTEGER PRIMARY KEY, emp_id INTEGER NOT NULL,
  amount INTEGER NOT NULL, sold_at TEXT NOT NULL
);
"""

DATASETS = {
    "basic": (
        """
        INSERT INTO departments VALUES (1,'Engineering'),(2,'Sales'),(3,'Empty');
        INSERT INTO employees VALUES
          (1,'Ada',1,200000,'2020-01-01'),
          (2,'Boris',1,150000,'2021-01-01'),
          (3,'Cara',1,150000,'2022-01-01'),
          (4,'Dana',2,120000,'2020-06-01'),
          (5,'Eli',2,90000,'2023-01-01');
        INSERT INTO sales VALUES
          (1,1,1000,'2024-01-15'),(2,1,2000,'2024-12-31'),
          (3,2,500,'2023-12-31'),(4,3,700,'2024-02-01'),
          (5,4,300,'2024-03-01'),(6,5,900,'2024-04-01');
        """,
        [
            ("Empty", 0, None, 0, None),
            ("Engineering", 3, 166666.67, 3700, "Ada"),
            ("Sales", 2, 105000.0, 1200, "Dana"),
        ],
    ),
    "ties_and_dates": (
        """
        INSERT INTO departments VALUES (1,'Alpha'),(2,'Beta'),(3,'Gamma');
        INSERT INTO employees VALUES
          (1,'Zoe',1,100000,'2020-01-01'),
          (2,'Amy',1,100000,'2020-01-01'),
          (3,'Bob',2,50000,'2020-01-01');
        INSERT INTO sales VALUES
          (1,1,100,'2024-01-01'),(2,2,200,'2025-01-01'),
          (3,2,300,'2023-12-31'),(4,3,400,'2024-12-31'),
          (5,3,500,'2024-06-15');
        """,
        [
            ("Alpha", 2, 100000.0, 100, "Amy"),
            ("Beta", 1, 50000.0, 900, "Bob"),
            ("Gamma", 0, None, 0, None),
        ],
    ),
    "rounding": (
        """
        INSERT INTO departments VALUES (1,'R');
        INSERT INTO employees VALUES
          (1,'A',1,100,'2020-01-01'),
          (2,'B',1,100,'2020-01-01'),
          (3,'C',1,101,'2020-01-01');
        INSERT INTO sales VALUES (1,1,0,'2024-02-02');
        """,
        [("R", 3, 100.33, 0, "C")],
    ),
}


def load_dataset(sql: str) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    con.executescript(sql)
    return con


try:
    with open(path, encoding="utf-8") as fh:
        query = fh.read().strip()
    if not query:
        raise ValueError("empty solution")
except Exception as exc:  # noqa: BLE001
    C.check("read query", lambda: (_ for _ in ()).throw(exc))
    C.report()

for name, (data, expected) in DATASETS.items():
    con = load_dataset(data)
    try:
        cur = con.execute(query)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
    except Exception as exc:  # noqa: BLE001
        C.check(f"{name}: query executes", lambda exc=exc: (_ for _ in ()).throw(exc))
        con.close()
        continue

    C.eq(f"{name}: column names", cols, ["dept_name", "headcount", "avg_salary", "total_sales_2024", "top_earner"])
    C.eq(f"{name}: row count", len(rows), len(expected))
    for i in range(max(len(rows), len(expected))):
        got = rows[i] if i < len(rows) else None
        want = expected[i] if i < len(expected) else None
        if got is None or want is None:
            C.eq(f"{name}: row {i}", got, want)
            continue
        for j, label in enumerate(["dept_name", "headcount", "avg_salary", "total_sales_2024", "top_earner"]):
            g, w = got[j], want[j]
            if j == 2 and isinstance(g, (int, float)) and isinstance(w, (int, float)):
                C.near(f"{name}: row {i} {label}", float(g), float(w), tol=0.005)
            else:
                C.eq(f"{name}: row {i} {label}", g, w)
    con.close()

# Reject a query that mutates the database.
con = load_dataset(DATASETS["basic"][0])
try:
    con.execute(query)
    after = con.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
    C.eq("query does not modify tables", after, 3)
except Exception:
    C.check("query does not modify tables", lambda: None)
con.close()

C.report()
