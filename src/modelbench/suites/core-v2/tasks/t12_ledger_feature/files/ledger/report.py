def account_balances(entries):
    """Return {account_code: natural_balance} for every account in the entries."""
    raise NotImplementedError("account_balances")


def trial_balance(entries):
    """Return [(code, name, natural_balance)] sorted by code, omitting zeros."""
    raise NotImplementedError("trial_balance")
