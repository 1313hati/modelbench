def merge_intervals(intervals):
    """Merge overlapping integer intervals [start, end].

    Returns a new list sorted by start. The input list must not be modified.
    """
    if not intervals:
        return []
    items = sorted((list(pair) for pair in intervals), key=lambda x: x[0])
    out = [items[0]]
    for start, end in items[1:]:
        last = out[-1]
        if start <= last[1]:
            last[1] = max(last[1], end)
        else:
            out.append([start, end])
    return out
