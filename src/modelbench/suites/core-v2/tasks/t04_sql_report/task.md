Write one SQLite query for the schema below.

```sql
CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE employees (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, dept_id INTEGER,
  salary INTEGER NOT NULL, hired_at TEXT NOT NULL
);
CREATE TABLE sales (
  id INTEGER PRIMARY KEY, emp_id INTEGER NOT NULL,
  amount INTEGER NOT NULL, sold_at TEXT NOT NULL
);
```

Return exactly these columns, in this order:

| column | meaning |
|---|---|
| `dept_name` | department name |
| `headcount` | number of employees in the department |
| `avg_salary` | average salary rounded to 2 decimal places; `NULL` when empty |
| `total_sales_2024` | sum of `amount` for that department's employees with `sold_at` in 2024; `0` when none |
| `top_earner` | name of the highest-paid employee in the department; ties go to the alphabetically first name; `NULL` when empty |

Rules:
- Include **every** department, including departments with no employees or sales.
- `sold_at` values are ISO dates such as `2024-03-01`; 2024 means the half-open
  range `[2024-01-01, 2025-01-01)`.
- Order rows by `dept_name` ascending.
- One statement only. No `CREATE`, `INSERT`, `PRAGMA` or temporary tables.

Return the query in a single ```sql block.
