Write `max_profit(jobs)` in Python. `jobs` is a list of `(start, end, profit)` tuples.

Return the maximum total profit of a set of pairwise non-overlapping jobs.
Intervals are half-open: `[start, end)`, so a job ending at 10 and another
starting at 10 do **not** overlap. All starts, ends and profits are integers,
`start < end`, and `profit > 0`.

Requirements:
- Do not modify or reorder the input list.
- Average `O(n log n)` time; no exponential search. It must handle 200,000 jobs
  in well under 3 seconds.
- Return an `int` (0 for no jobs).

Example: `max_profit([(1,3,50),(2,4,10),(3,5,40)])` is `90` (jobs 1 and 3).

Return the complete file. Standard library only.
