from .models import Account

CHART = {
    "1000": Account("1000", "Cash", "asset"),
    "1100": Account("1100", "Receivables", "asset"),
    "2000": Account("2000", "Payables", "liability"),
    "3000": Account("3000", "Equity", "equity"),
    "4000": Account("4000", "Revenue", "revenue"),
    "5000": Account("5000", "Expenses", "expense"),
}

NORMAL_SIGN = {
    "asset": 1,
    "expense": 1,
    "liability": -1,
    "equity": -1,
    "revenue": -1,
}


def get_account(code):
    try:
        return CHART[code]
    except KeyError:
        raise ValueError(f"unknown account {code}") from None


def normal_sign(kind):
    try:
        return NORMAL_SIGN[kind]
    except KeyError:
        raise ValueError(f"unknown account kind {kind}") from None
