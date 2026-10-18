from collections import Counter


def count_pairs(nums, target):
    seen = Counter()
    count = 0
    for value in nums:
        count += seen.get(target - value, 0)
        seen[value] += 1
    return count
