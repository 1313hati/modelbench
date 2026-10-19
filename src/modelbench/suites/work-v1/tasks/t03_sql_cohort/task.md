# Monthly retention report

Write **one SQLite query** that produces monthly cohort retention from this schema:

```sql
CREATE TABLE users  (id INTEGER PRIMARY KEY, signup_date TEXT NOT NULL); -- 'YYYY-MM-DD'
CREATE TABLE events (user_id INTEGER NOT NULL, event_date TEXT NOT NULL, kind TEXT NOT NULL);
```

## Output

Exactly these five columns, in this order:

| column | meaning |
|---|---|
| `cohort` | signup month, `YYYY-MM` |
| `users` | number of users who signed up in that month |
| `m1` | share of those users with at least one `kind = 'active'` event in the **first** calendar month after signup |
| `m2` | same, for the second calendar month |
| `m3` | same, for the third calendar month |

`m1`–`m3` are text produced with `printf('%.1f', value)`, for example `66.7`,
with no percent sign. A user with no qualifying event counts towards the
denominator and contributes `0.0`.

## Rules

1. Calendar months, not 30-day windows: a user who signs up on 31 January has
   their first month in February.
2. Events in the signup month itself, or later than the third month, are ignored.
3. Only `kind = 'active'` events count.
4. One row per cohort, ordered by `cohort` ascending.
5. The query must work on any data with this schema — your answer is run against
   a second, unpublished dataset.

Return the query in a ```sql fence. No comments, no extra statements.
