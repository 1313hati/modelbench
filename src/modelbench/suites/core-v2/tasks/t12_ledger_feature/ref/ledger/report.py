from .accounts import get_account, normal_sign


def _totals(entries):
    totals = {}
    for entry in entries:
        for posting in entry.postings:
            get_account(posting.account)
            totals[posting.account] = totals.get(posting.account, 0) + posting.amount
    return totals


def account_balances(entries):
    """Return {account_code: natural_balance} for every account in the entries."""
    totals = _totals(entries)
    return {
        code: amount * normal_sign(get_account(code).kind)
        for code, amount in totals.items()
    }


def trial_balance(entries):
    """Return [(code, name, natural_balance)] sorted by code, omitting zeros."""
    balances = account_balances(entries)
    return [
        (code, get_account(code).name, balance)
        for code, balance in sorted(balances.items())
        if balance != 0
    ]
