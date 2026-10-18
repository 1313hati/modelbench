WITH dept_sales AS (
    SELECT e.dept_id, SUM(s.amount) AS total
    FROM sales s
    JOIN employees e ON e.id = s.emp_id
    WHERE s.sold_at >= '2024-01-01' AND s.sold_at < '2025-01-01'
    GROUP BY e.dept_id
),
ranked AS (
    SELECT e.dept_id, e.name,
           ROW_NUMBER() OVER (PARTITION BY e.dept_id ORDER BY e.salary DESC, e.name ASC) AS rn
    FROM employees e
    WHERE e.dept_id IS NOT NULL
)
SELECT d.name AS dept_name,
       COUNT(e.id) AS headcount,
       ROUND(AVG(e.salary), 2) AS avg_salary,
       COALESCE(ds.total, 0) AS total_sales_2024,
       (SELECT r.name FROM ranked r WHERE r.dept_id = d.id AND r.rn = 1) AS top_earner
FROM departments d
LEFT JOIN employees e ON e.dept_id = d.id
LEFT JOIN dept_sales ds ON ds.dept_id = d.id
GROUP BY d.id, d.name, ds.total
ORDER BY d.name ASC
