def parse_csv(text):
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if text == "":
        return []

    records = []
    row = []
    field = []
    quoted = False
    after_quote = False
    i = 0
    n = len(text)

    def end_record():
        nonlocal row, field, after_quote
        row.append("".join(field))
        records.append(row)
        row = []
        field = []
        after_quote = False

    while i < n:
        ch = text[i]
        if quoted:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                else:
                    quoted = False
                    after_quote = True
                    i += 1
            else:
                field.append(ch)
                i += 1
            continue

        if after_quote:
            if ch == ",":
                row.append("".join(field))
                field = []
                after_quote = False
                i += 1
            elif ch == "\n":
                end_record()
                i += 1
            elif ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                end_record()
                i += 2
            else:
                raise ValueError("unexpected character after closing quote")
            continue

        if ch == '"':
            if field:
                raise ValueError("quote inside unquoted field")
            quoted = True
            i += 1
        elif ch == ",":
            row.append("".join(field))
            field = []
            i += 1
        elif ch == "\n":
            end_record()
            i += 1
        elif ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                end_record()
                i += 2
            else:
                raise ValueError("bare CR")
        else:
            field.append(ch)
            i += 1

    if quoted:
        raise ValueError("unterminated quoted field")
    if row or field or after_quote:
        row.append("".join(field))
        records.append(row)
    return records


def write_csv(rows):
    if not isinstance(rows, (list, tuple)):
        raise ValueError("rows must be a list or tuple")
    out = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError("each row must be a non-empty list or tuple")
        cells = []
        for value in row:
            if not isinstance(value, str):
                raise ValueError("fields must be strings")
            if any(ch in value for ch in ',"\r\n'):
                cells.append('"' + value.replace('"', '""') + '"')
            else:
                cells.append(value)
        out.append(",".join(cells) + "\r\n")
    return "".join(out)
