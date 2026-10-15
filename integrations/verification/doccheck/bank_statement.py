"""
Document checking — Layer 2: bank-statement checks.

The headline check is running-balance reconciliation: for every row,
    balance == previous_balance + credits - debits
If one row breaks, that row was almost certainly edited. This is the single
strongest HONEST automated signal — it's arithmetic, not a guess, and every
flag points to the exact row so a lender can see why.

Input shape (produced by the OCR/extraction layer) — `extracted['transactions']`
is a list of dicts, oldest first:
    {'date': date, 'description': str, 'debit': Decimal, 'credit': Decimal,
     'balance': Decimal}
Plus optional 'opening_balance' / 'closing_balance'.
"""

from decimal import Decimal
from .framework import CheckResult, Outcome

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.02")   # allow 2 cents for rounding noise in OCR


def check_running_balance(extracted, context):
    """STRONG. Every row's balance must follow from the previous one."""
    txns = extracted.get("transactions") or []
    if len(txns) < 2:
        return CheckResult(
            "balance_reconciles", "Running balance reconciles",
            Outcome.INCONCLUSIVE, "strong",
            "Not enough transactions were read to check the running balance.")

    broken = []
    opening = _dec(extracted.get("opening_balance"))

    # Anchor row 1 to the opening balance when we have one, so the FIRST row's
    # credit/debit is validated too — not only the row-to-row deltas. Without
    # this, editing the first row's credit and its balance together would slip
    # through the delta checks below.
    if opening is not None:
        first = txns[0]
        bal0 = _dec(first.get("balance"))
        if bal0 is not None:
            expected0 = (opening + _dec(first.get("credit")) - _dec(first.get("debit"))).quantize(CENT)
            if abs(expected0 - bal0) > TOLERANCE:
                broken.append({
                    "row": 1,
                    "date": str(first.get("date")),
                    "expected": str(expected0),
                    "shown": str(bal0),
                })

    for i in range(1, len(txns)):
        prev_bal = _dec(txns[i - 1].get("balance"))
        bal = _dec(txns[i].get("balance"))
        debit = _dec(txns[i].get("debit"))
        credit = _dec(txns[i].get("credit"))
        if prev_bal is None or bal is None:
            continue  # can't check this row; not a fail
        expected = (prev_bal + credit - debit).quantize(CENT)
        if abs(expected - bal) > TOLERANCE:
            broken.append({
                "row": i + 1,
                "date": str(txns[i].get("date")),
                "expected": str(expected),
                "shown": str(bal),
            })

    if broken:
        first = broken[0]
        return CheckResult(
            "balance_reconciles", "Running balance reconciles",
            Outcome.FAIL, "strong",
            detail=(f"The running balance does not add up at row {first['row']} "
                    f"({first['date']}): expected M{first['expected']} but the "
                    f"statement shows M{first['shown']}. "
                    f"{len(broken)} row(s) affected."),
            data={"broken_rows": broken})

    return CheckResult(
        "balance_reconciles", "Running balance reconciles",
        Outcome.PASS, "strong",
        detail="Every transaction's balance follows correctly from the previous one.")


def check_dates_sequential(extracted, context):
    """MODERATE. Transaction dates should move forward (oldest first)."""
    txns = extracted.get("transactions") or []
    dates = [t.get("date") for t in txns if t.get("date")]
    if len(dates) < 2:
        return CheckResult(
            "dates_sequential", "Dates in order",
            Outcome.INCONCLUSIVE, "moderate",
            "Not enough dated rows to check ordering.")
    out_of_order = sum(1 for a, b in zip(dates, dates[1:]) if b < a)
    if out_of_order:
        return CheckResult(
            "dates_sequential", "Dates in order",
            Outcome.FAIL, "moderate",
            f"{out_of_order} transaction date(s) go backwards — rows may have "
            f"been inserted or edited.")
    return CheckResult(
        "dates_sequential", "Dates in order",
        Outcome.PASS, "moderate", "Transaction dates run in order.")


def check_opening_closing(extracted, context):
    """MODERATE. Stated opening/closing balances should match first/last row."""
    txns = extracted.get("transactions") or []
    if not txns:
        return None
    results_ok = True
    details = []
    opening = _dec(extracted.get("opening_balance"))
    closing = _dec(extracted.get("closing_balance"))

    if opening is not None:
        # First row's balance should equal opening ± its own movement.
        first = txns[0]
        expected_first = (opening + _dec(first.get("credit")) - _dec(first.get("debit"))).quantize(CENT)
        shown_first = _dec(first.get("balance"))
        if shown_first is not None and abs(expected_first - shown_first) > TOLERANCE:
            results_ok = False
            details.append(f"opening balance M{opening} doesn't lead to first "
                           f"row balance M{shown_first}")

    if closing is not None:
        shown_last = _dec(txns[-1].get("balance"))
        if shown_last is not None and abs(closing - shown_last) > TOLERANCE:
            results_ok = False
            details.append(f"stated closing balance M{closing} ≠ last row "
                           f"balance M{shown_last}")

    if opening is None and closing is None:
        return CheckResult(
            "opening_closing", "Opening/closing balances match",
            Outcome.INCONCLUSIVE, "moderate",
            "No stated opening/closing balance was read.")
    if not results_ok:
        return CheckResult(
            "opening_closing", "Opening/closing balances match",
            Outcome.FAIL, "moderate", "; ".join(details) + ".")
    return CheckResult(
        "opening_closing", "Opening/closing balances match",
        Outcome.PASS, "moderate", "Opening and closing balances line up with the rows.")


def _dec(v):
    if v is None or v == "":
        return Decimal("0") if v == 0 else None
    try:
        return Decimal(str(v))
    except Exception:
        return None


BANK_STATEMENT_CHECKS = [
    check_running_balance,
    check_dates_sequential,
    check_opening_closing,
]