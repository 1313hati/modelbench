def allocate(total, weights):
    """Split `total` proportional to `weights` using largest remainders."""
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("total must be a non-negative integer")
    if not isinstance(weights, (list, tuple)) or not weights:
        raise ValueError("weights must be a non-empty list or tuple")
    for weight in weights:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            raise ValueError("weights must be positive integers")

    denominator = sum(weights)
    raw = [total * weight for weight in weights]
    shares = [value // denominator for value in raw]
    remaining = total - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] % denominator), i))
    for index in order[:remaining]:
        shares[index] += 1
    return shares
