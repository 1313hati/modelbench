Write `chunked(iterable, size, overlap=0)` in Python, a generator of overlapping tuples.

Rules:
- `step = size - overlap`. Emit `tuple` chunks starting at indices `0, step, 2*step, ...` while the
  start index is below the number of items. A chunk holds up to `size` items, so the last one may be
  shorter. No padding, and a chunk that would contain only items already emitted is not produced.
- `size` must be an `int >= 1`; `overlap` must be an `int` with `0 <= overlap < size`. Anything else
  (including booleans, floats, strings) raises `ValueError`.
- Must work with any iterable, including generators and infinite iterators, consuming only as much as
  needed (at most one chunk ahead) — never materialize the whole input.
- An empty input yields nothing.

Examples: `list(chunked(range(5), 3, 1))` is `[(0, 1, 2), (2, 3, 4)]`;
`list(chunked(range(7), 3))` is `[(0, 1, 2), (3, 4, 5), (6,)]`;
`list(chunked(range(3), 3, 1))` is `[(0, 1, 2)]`, because the next chunk would repeat items only.

Return the complete file.
