from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    kind: str


@dataclass(frozen=True)
class Posting:
    account: str
    amount: int


@dataclass(frozen=True)
class Entry:
    id: str
    postings: Tuple[Posting, ...]
