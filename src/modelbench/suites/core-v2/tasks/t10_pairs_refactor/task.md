The following function is correct but too slow for production:

```python
def count_pairs(nums, target):
    count = 0
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                count += 1
    return count
```

Rewrite it as an `O(n)` average-time function with the same name, signature and
exact behaviour. Return the **number of index pairs** `i < j` whose values sum to
`target`. Duplicates are distinct indices: `[1, 1, 1]` with target 2 has three
pairs.

Requirements:
- Do not mutate `nums`.
- Handle negative numbers, zero and large values.
- 200,000 integers must finish in under 1.5 seconds.
- Return an `int`.
- Standard library only.

Return the complete file.
