from .accounts import get_account


def validate_entry(entry):
    """Double-entry check: at least two postings, known accounts, sum zero."""
    if len(entry.postings) < 2:
        raise ValueError("an entry needs at least two postings")
    total = 0
    for posting in entry.postings:
        get_account(posting.account)
        if isinstance(posting.amount, bool) or not isinstance(posting.amount, int):
            raise ValueError("posting amounts must be integers")
        total += posting.amount
    if total != 0:
        raise ValueError("entry does not balance")
    return entry
