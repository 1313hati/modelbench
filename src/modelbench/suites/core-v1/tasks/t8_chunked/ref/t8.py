def chunked(iterable, size, overlap=0):
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("size must be an integer >= 1")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or not (0 <= overlap < size):
        raise ValueError("overlap must be an integer with 0 <= overlap < size")

    step = size - overlap
    source = iter(iterable)
    buf = []
    emitted = False
    while True:
        added = 0
        while len(buf) < size:
            try:
                buf.append(next(source))
                added += 1
            except StopIteration:
                break
        if not buf:
            return
        if emitted and added == 0 and len(buf) <= overlap:
            return
        yield tuple(buf)
        emitted = True
        if len(buf) < size:
            return
        del buf[:step]
