from collections import Counter


def top_k_frequent(nums, k):
    counts = Counter(nums)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [value for value, _ in ranked[:k]]
