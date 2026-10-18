MIN = -(2**63)
MAX = 2**63 - 1


def _zigzag(value):
    return (value << 1) ^ (value >> 63)


def encode_varints(values):
    if not isinstance(values, (list, tuple)):
        raise ValueError("values must be a list or tuple")
    out = bytearray()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("values must be integers")
        if value < MIN or value > MAX:
            raise ValueError("value outside signed 64-bit range")
        unsigned = _zigzag(value)
        while True:
            byte = unsigned & 0x7F
            unsigned >>= 7
            if unsigned:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
    return bytes(out)


def decode_varints(data):
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("data must be bytes")
    values = []
    i = 0
    n = len(data)
    while i < n:
        unsigned = 0
        shift = 0
        count = 0
        while True:
            if i >= n:
                raise ValueError("truncated varint")
            byte = data[i]
            i += 1
            count += 1
            if count > 10:
                raise ValueError("varint too long")
            if count == 10 and byte > 1:
                raise ValueError("varint overflows 64 bits")
            unsigned |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        if count > 1 and (byte & 0x7F) == 0:
            raise ValueError("non-canonical varint")
        values.append((unsigned >> 1) ^ -(unsigned & 1))
    return values
