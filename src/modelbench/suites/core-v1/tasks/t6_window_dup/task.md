Write `has_duplicate_within_k(nums: list[int], k: int) -> bool` in Python.

It returns `True` when the same value appears at two indices `i < j` with `j - i <= k`.
Return `False` otherwise. If `k < 1`, raise `ValueError`.

Examples: `has_duplicate_within_k([1,2,3,1], 3)` is `True`, with `k=2` it is `False`.

Requirements:
- Average O(n) time. No nested loops over the input.
- It must handle 200,000 elements in well under 2 seconds.
- Do not modify the input list.

Return the complete file.
