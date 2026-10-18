from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Room:
    id: str
    capacity: int
    nightly_rate: int
    weekend_rate: int


@dataclass(frozen=True)
class Reservation:
    id: str
    room_id: str
    start: date
    end: date
    guests: int = 1


def parse_date(value: str) -> date:
    return date.fromisoformat(value)
