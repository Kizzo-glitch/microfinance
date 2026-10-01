"""
Fedha-Grow — LAYER 3: instalment schedule & total cost (KFS Sections 5 & 6)
===========================================================================
Computes the month-by-month repayment schedule (principal / interest / fees /
balance per instalment) and the total cost of credit, from the loan amount,
term, product rate, and product fees.

Pure functions — no Django needed — so the maths is testable in isolation.
Supports flat and reducing-balance interest.

The KFS shows this as an authoritative disclosure, so the numbers must be exact
and reconcile: sum of instalment totals == total amount payable.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP


def _money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Instalment:
    number: int
    due_date: object          # date or None (view fills real dates)
    principal: Decimal
    interest: Decimal
    fees: Decimal
    total: Decimal
    balance: Decimal          # remaining principal after this instalment


@dataclass
class CostBreakdown:
    principal: Decimal
    total_interest: Decimal
    fees_by_type: dict        # {fee_type: amount charged over the loan}
    total_fees: Decimal
    total_payable: Decimal
    instalments: list = field(default_factory=list)


def _total_interest_flat(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """Flat interest: rate applied to full principal for the whole term."""
    return _money(principal * (annual_rate / Decimal("100")) * (Decimal(term_months) / Decimal("12")))


def build_schedule(*, principal, annual_rate, term_months, fees,
                   interest_type="flat"):
    """
    fees: list of dicts {fee_type, amount, basis, applicable} (from ProductFee).
    Only fees that are applicable AND fall within the schedule are spread here:
      - once_origination / once_predisbursement -> added to instalment 1
      - per_instalment -> added to every instalment
      - others (per_occurrence, as_incurred, conditional, na) -> NOT scheduled
        (they're contingent; disclosed in the fees table, not the schedule).
    """
    principal = _money(principal)
    annual_rate = Decimal(str(annual_rate))
    n = int(term_months)

    # --- interest ---
    if interest_type == "flat":
        total_interest = _total_interest_flat(principal, annual_rate, n)
        interest_per = _money(total_interest / n)
    else:  # reducing balance
        total_interest, interest_per = Decimal("0.00"), None  # computed per-period below

    # --- scheduled fees ---
    applicable = [f for f in fees if f.get("applicable")]
    once_fees = sum((_money(f["amount"]) for f in applicable
                     if f["basis"] in ("once_origination", "once_predisbursement")), Decimal("0.00"))
    per_inst_fee = sum((_money(f["amount"]) for f in applicable
                        if f["basis"] == "per_instalment"), Decimal("0.00"))

    instalments = []
    balance = principal
    principal_per = _money(principal / n)

    for i in range(1, n + 1):
        # principal component (last instalment absorbs rounding)
        if i < n:
            p = principal_per
        else:
            p = balance   # clear the remainder exactly

        # interest component
        if interest_type == "flat":
            intr = interest_per if i < n else _money(total_interest - interest_per * (n - 1))
        else:
            intr = _money(balance * (annual_rate / Decimal("100")) / Decimal("12"))
            total_interest += intr

        # fees on this instalment
        f = per_inst_fee + (once_fees if i == 1 else Decimal("0.00"))

        total = _money(p + intr + f)
        balance = _money(balance - p)
        instalments.append(Instalment(
            number=i, due_date=None, principal=_money(p), interest=_money(intr),
            fees=_money(f), total=total, balance=max(balance, Decimal("0.00"))))

    total_interest = _money(total_interest)

    # --- cost breakdown (all applicable fees, incl. contingent, for the table) ---
    fees_by_type = {}
    for fee in applicable:
        amt = _money(fee["amount"])
        # scheduled fees count once/per-instalment toward total; contingent shown but not summed
        if fee["basis"] == "per_instalment":
            amt = _money(amt * n)
        elif fee["basis"] in ("once_origination", "once_predisbursement"):
            pass  # once
        else:
            amt = Decimal("0.00")  # contingent — disclosed, not included in total payable
        fees_by_type[fee["fee_type"]] = fees_by_type.get(fee["fee_type"], Decimal("0.00")) + amt

    total_fees = _money(sum(fees_by_type.values(), Decimal("0.00")))
    total_payable = _money(principal + total_interest + total_fees)

    return CostBreakdown(
        principal=principal, total_interest=total_interest,
        fees_by_type=fees_by_type, total_fees=total_fees,
        total_payable=total_payable, instalments=instalments)