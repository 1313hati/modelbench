This function is wrong. A hidden test failed with:

```
AssertionError: top_k_frequent([1, 1, 1, 2, 2, 3], 2) == [1, 2]
E   assert [3, 2] == [1, 2]
```

```python
from collections import Counter
import heapq


def top_k_frequent(nums, k):
    counts = Counter(nums)
    return heapq.nlargest(k, counts)
```

Fix it. `k` is always 1 <= k <= number of distinct values. Return the `k` most frequent values as a
list, most frequent first; ties are broken by the smaller value first.
Keep the function name and make it return exactly that list.

Return the complete file.
