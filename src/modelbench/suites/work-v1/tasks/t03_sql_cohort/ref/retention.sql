WITH offsets AS (
  SELECT
    u.id,
    strftime('%Y-%m', u.signup_date) AS cohort,
    (CAST(strftime('%Y', e.event_date) AS INTEGER) - CAST(strftime('%Y', u.signup_date) AS INTEGER)) * 12
      + (CAST(strftime('%m', e.event_date) AS INTEGER) - CAST(strftime('%m', u.signup_date) AS INTEGER)) AS offset
  FROM users u
  LEFT JOIN events e
    ON e.user_id = u.id
   AND e.kind = 'active'
)
SELECT
  cohort,
  COUNT(DISTINCT id) AS users,
  printf('%.1f', 100.0 * COUNT(DISTINCT CASE WHEN offset = 1 THEN id END) / COUNT(DISTINCT id)) AS m1,
  printf('%.1f', 100.0 * COUNT(DISTINCT CASE WHEN offset = 2 THEN id END) / COUNT(DISTINCT id)) AS m2,
  printf('%.1f', 100.0 * COUNT(DISTINCT CASE WHEN offset = 3 THEN id END) / COUNT(DISTINCT id)) AS m3
FROM offsets
GROUP BY cohort
ORDER BY cohort;
