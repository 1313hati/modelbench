from .models import Posting


def parse_dollars(text):
    """Parse a two-decimal dollar string into integer cents without floats."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("amount must be text")
    text = text.strip()
    sign = 1
    if text[0] in "+-":
        if text[0] == "-":
            sign = -1
        text = text[1:]
    if text.count(".") > 1:
        raise ValueError("invalid amount")
    if "." in text:
        whole, frac = text.split(".")
    else:
        whole, frac = text, ""
    if not whole.isdigit() or (frac and not frac.isdigit()) or len(frac) > 2:
        raise ValueError("invalid amount")
    frac = (frac + "00")[:2]
    return sign * (int(whole) * 100 + int(frac))


def posting_from_row(account, amount_text):
    return Posting(account, parse_dollars(amount_text))
