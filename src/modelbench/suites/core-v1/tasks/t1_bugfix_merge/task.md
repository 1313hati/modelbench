Fix the bugs in `merge_intervals` below. Keep the name, signature and docstring contract.

```python
def merge_intervals(intervals):
    """Merge overlapping integer intervals [start, end].

    Returns a new list sorted by start. The input list must not be modified.
    """
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    out = [intervals[0]]
    for start, end in intervals[1:]:
        last = out[-1]
        if start < last[1]:
            last[1] = max(last[1], end)
        else:
            out.append([start, end])
    return out
```

This version passes the obvious cases but fails hidden tests on at least two edge cases.
Return the complete corrected file.
