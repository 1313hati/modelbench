from datetime import timedelta

TAX_PERCENT = 8


def _round_half_up(numerator: int, denominator: int) -> int:
    return (numerator + denominator // 2) // denominator


def discount_percent(nights: int) -> int:
    if nights >= 7:
        return 10
    return 0


def quote(room, start, end) -> dict:
    nights = (end - start).days
    if nights <= 0:
        raise ValueError("end must be after start")

    room_total = 0
    for offset in range(nights):
        day = start + timedelta(days=offset)
        if day.weekday() in (5, 6):
            room_total += room.weekend_rate
        else:
            room_total += room.nightly_rate

    percent = discount_percent(nights)
    discount = room_total * percent // 100
    tax = _round_half_up(room_total * TAX_PERCENT, 100)
    total = room_total - discount + tax
    return {
        "nights": nights,
        "room_total": room_total,
        "discount": discount,
        "tax": tax,
        "total": total,
    }
