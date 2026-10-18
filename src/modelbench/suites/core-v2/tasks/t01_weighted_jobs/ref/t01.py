from bisect import bisect_right


def max_profit(jobs):
    if not jobs:
        return 0
    items = sorted(jobs, key=lambda job: (job[1], job[0]))
    ends = [job[1] for job in items]
    best = [0] * (len(items) + 1)
    for i, (start, _end, profit) in enumerate(items, 1):
        compatible = bisect_right(ends, start, 0, i - 1)
        take = best[compatible] + profit
        best[i] = max(best[i - 1], take)
    return best[-1]
