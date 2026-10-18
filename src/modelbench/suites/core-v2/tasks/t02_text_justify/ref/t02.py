def justify(words, width):
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("width must be an integer >= 1")
    for word in words:
        if not isinstance(word, str) or not word or any(ch.isspace() for ch in word):
            raise ValueError("words must be non-empty strings without whitespace")
        if len(word) > width:
            raise ValueError("word longer than width")
    if not words:
        return []

    lines = []
    current = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if length + extra <= width:
            current.append(word)
            length += extra
        else:
            lines.append((current, length))
            current = [word]
            length = len(word)
    lines.append((current, length))

    out = []
    for index, (line, used) in enumerate(lines):
        if index == len(lines) - 1 or len(line) == 1:
            out.append(" ".join(line))
            continue
        gaps = len(line) - 1
        spaces = width - (used - gaps)
        base, rem = divmod(spaces, gaps)
        parts = [line[0]]
        for i, word in enumerate(line[1:]):
            parts.append(" " * (base + (1 if i < rem else 0)))
            parts.append(word)
        out.append("".join(parts))
    return out
