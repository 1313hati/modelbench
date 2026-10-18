Implement an LRU cache in Python:

```python
class LRUCache:
    def __init__(self, capacity: int): ...
    def get(self, key) -> int: ...
    def put(self, key: int, value: int) -> None: ...
```

Rules:
- `capacity` must be a positive integer; otherwise raise `ValueError` (also for `0`, negative, `True`/`False`).
- `get` returns the stored value and marks that key as most recently used; unknown keys return `-1`.
- `put` inserts or updates. Updating an existing key changes its value and marks it most recently used.
  Adding a key past capacity evicts the least recently used key.
- Both operations must be O(1) average time — no list scans or sorting inside get/put.

Return the complete file. Standard library only.
