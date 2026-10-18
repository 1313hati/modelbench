from collections import deque


def has_duplicate_within_k(nums, k):
    if k < 1:
        raise ValueError("k must be >= 1")
    window = set()
    recent = deque()
    for value in nums:
        if value in window:
            return True
        window.add(value)
        recent.append(value)
        if len(recent) > k:
            window.discard(recent.popleft())
    return False
