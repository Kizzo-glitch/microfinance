"""
Loan schedule builders for Fedha-Grow.

CBL's Financial Consumer Protection Act mandates the declining-balance method:
interest each period is charged on the OUTSTANDING principal, which shrinks as
the loan is repaid. The flat method (interest on the original principal for the
whole term) is the practice the Act prohibits — it roughly doubles the true
interest. These builders implement only the lawful method.

Two product shapes, one module:
  - build_schedule            : instalment loans — DECLINING-BALANCE (EMI).
  - build_month_end_schedule  : single-repayment month-end products (a flat
                                monthly fee, one repayment at month-end). This
                                is a single-charge product, NOT instalment
                                interest, so the declining-balance rule does
                                not apply to it.

EMI = P*r*(1+r)^n / ((1+r)^n - 1)   (r = monthly rate; r == 0 -> P/n).
Verified against CBL's worked example (M10,000, 24% p.a., 12 months,
M200 initiation, M50/month service): EMI M945.60, total payable M12,147.15,
credit-cost multiple 1.21 — matching to the cent.

ONE Instalment dataclass, ONE money helper. Flat-interest instalment logic is
not present — the Act prohibits it, and a 'flat' interest_type is refused.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP


def _m(x) -> Decimal:
    """Quantize to cents, half-up — the money rounding used everywhere here."""
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Instalment:
    number: int
    principal: Decimal
    interest: Decimal
    fees: Decimal
    total: Decimal
    balance: Decimal              # remaining principal after this instalment
    due_date: object = None       # view fills real dates; optional here


@dataclass
class ScheduleResult:
    principal: Decimal
    total_interest: Decimal
    total_fees: Decimal
    fees_by_type: dict
    total_payable: Decimal
    instalments: list = field(default_factory=list)
    method: str = "declining_balance"
    emi: Decimal = Decimal("0.00")


# ───────────────────────── instalment (declining balance) ──────────────────

def build_schedule(*, principal, annual_rate, term_months, fees=None,
                   interest_type="reducing"):
    """
    Build a declining-balance (EMI) instalment schedule.

    principal     : Decimal loan amount.
    annual_rate   : Decimal annual interest rate, percent (e.g. 24 for 24%).
    term_months   : int number of monthly instalments.
    fees          : list of {fee_type, amount(Decimal), basis, applicable}.
                    'basis' decides how each fee is spread:
                      - 'monthly'/'per_instalment'/'instalment' -> every row
                      - anything else (origination/once/upfront) -> row 1
    interest_type : only the declining-balance path is lawful. 'flat' is
                    REFUSED (raises ValueError) so a flat product can never
                    silently produce a schedule.

    Returns a ScheduleResult. The sum of instalment totals reconciles exactly
    to total_payable, and the final-row balance lands on 0.00.
    """
    if interest_type == "flat":
        raise ValueError(
            "Flat-interest schedules are not permitted — the CBL Act mandates "
            "the declining-balance method. Set interest_type to 'reducing'.")

    P = _m(principal)
    n = int(term_months)
    r = Decimal(str(annual_rate)) / Decimal("100") / Decimal("12")

    # split fees: upfront (origination) vs per-instalment (monthly/service)
    fees = fees or []
    upfront_fee = Decimal("0")
    monthly_fee = Decimal("0")
    fees_by_type = {}
    for f in fees:
        if not f.get("applicable", True):
            continue
        amt = Decimal(str(f.get("amount", 0)))
        fees_by_type[f.get("fee_type", "fee")] = str(amt)
        basis = (f.get("basis") or "").lower()
        if "month" in basis or "instalment" in basis or "installment" in basis:
            monthly_fee += amt
        else:
            upfront_fee += amt

    # EMI = P*r*(1+r)^n / ((1+r)^n - 1) ; r == 0 -> straight principal split
    if r == 0:
        emi = P / Decimal(n)
    else:
        pow_n = (Decimal("1") + r) ** n
        emi = P * r * pow_n / (pow_n - Decimal("1"))
    emi = _m(emi)

    instalments = []
    balance = P
    total_interest = Decimal("0")
    total_fees = Decimal("0")

    for i in range(1, n + 1):
        interest = _m(balance * r)
        principal_part = emi - interest
        if i == n:
            principal_part = balance          # sweep rounding drift into last row
        balance = _m(balance - principal_part)

        fee_this = _m(monthly_fee)
        if i == 1:
            fee_this = _m(fee_this + upfront_fee)

        row_total = _m(principal_part + interest + fee_this)
        total_interest += interest
        total_fees += fee_this

        instalments.append(Instalment(
            number=i,
            principal=_m(principal_part),
            interest=_m(interest),
            fees=fee_this,
            total=row_total,
            balance=balance if balance > 0 else Decimal("0.00"),
        ))

    total_payable = _m(P + total_interest + total_fees)

    # Reconciliation guarantee: sum of instalment totals == total_payable.
    summed = _m(sum(r.total for r in instalments))
    if summed != total_payable:
        diff = total_payable - summed
        instalments[-1].total = _m(instalments[-1].total + diff)
        instalments[-1].principal = _m(instalments[-1].principal + diff)

    return ScheduleResult(
        principal=P,
        total_interest=_m(total_interest),
        total_fees=_m(total_fees),
        fees_by_type=fees_by_type,
        total_payable=total_payable,
        instalments=instalments,
        method="declining_balance",
        emi=emi,
    )


# ───────────────────────── single repayment (month-end) ────────────────────

def build_month_end_schedule(principal, product, disbursement_date):
    """
    Single-repayment month-end product: one flat monthly fee, one repayment at
    month-end. A single-charge product, NOT instalment interest, so the
    declining-balance rule doesn't apply.

    principal         : Decimal loan amount.
    product           : LenderProduct with flat_monthly_fee_rate (Decimal %)
                        and month_end_due_date(disbursement_date).
    disbursement_date : date the loan is disbursed (drives the due date).

    Returns a dict (distinct shape from ScheduleResult — callers branch on
    product.repayment_structure). Reconciliation is exact by construction: the
    single instalment equals the total payable.
    """
    principal = _m(principal)
    fee_rate = product.flat_monthly_fee_rate            # e.g. Decimal('15.00')
    fee = _m(principal * fee_rate / Decimal("100"))
    total_payable = _m(principal + fee)
    due_date = product.month_end_due_date(disbursement_date)

    return {
        "structure": "single_month_end",
        "principal": principal,
        "total_interest": fee,
        "total_fees": Decimal("0.00"),
        "total_payable": total_payable,
        "instalment_count": 1,
        "instalments": [{
            "number": 1,
            "due_date": due_date,
            "principal": principal,
            "interest": fee,
            "fees": Decimal("0.00"),
            "amount": total_payable,
            "total": total_payable,
            "balance_after": _m(0),
        }],
        "interest_note": (
            f"Flat fee of {fee_rate}% of the loan amount for the month, "
            f"regardless of the day you borrow. One repayment of "
            f"M{total_payable} is due on {due_date:%d %B %Y} (month-end)."
        ),
        "reconciles": True,
    }