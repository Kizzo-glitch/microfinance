"""
Fedha-Grow — what a borrower owes, and when
===========================================
Instalment amounts come from the loan's Key Facts Statement (the schedule the
borrower acknowledged). Due dates count monthly from the first payment date.
Loans without a KFS (older ones) fall back to the monthly instalment.

Only CONFIRMED payments count as paid, the same rule as the loan balance.
Nothing here ever exceeds the outstanding balance.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from loans.pricing import money

ZERO = Decimal("0.00")


@dataclass
class Instalment:
    number: int
    due_date: date
    amount: Decimal


@dataclass
class AmountsDue:
    due_now: Decimal            # every instalment due by today, minus what's paid
    next_amount: Decimal        # what's left of the earliest unpaid instalment
    next_due_date: date | None
    overdue_count: int          # instalments past their date and not fully paid
    paid: Decimal
    outstanding: Decimal


def instalments(loan) -> list[Instalment]:
    from loans.models import KeyFactsStatement   # avoid an import cycle

    kfs = KeyFactsStatement.objects.filter(loan_id=loan.pk).first()
    rows = ((kfs.snapshot or {}).get("schedule") if kfs else None) or []
    amounts = [money(r["total"]) for r in rows if r.get("total") not in (None, "")]

    if not amounts:   # legacy loan: equal instalments that add up to the total
        try:
            n = max(int(loan.loan_term), 1)
        except (TypeError, ValueError):
            n = 1
        total = money(loan.total_repayable or 0)
        each = money(loan.monthly_installment or (total / n))
        amounts = [each] * (n - 1) + [max(total - each * (n - 1), ZERO)]

    if len(amounts) == 1 and loan.due_date:
        return [Instalment(1, loan.due_date, amounts[0])]
    first = loan.first_payment_date
    return [Instalment(i + 1, first + relativedelta(months=i), amt)
            for i, amt in enumerate(amounts)]


def amounts_due(loan, today=None) -> AmountsDue:
    from loans.models import LoanPayment

    today = today or timezone.localdate()
    paid = money(LoanPayment.confirmed_total(loan))
    outstanding = money(loan.outstanding_balance or 0)
    rows = instalments(loan)

    due_by_today = sum((r.amount for r in rows if r.due_date <= today), ZERO)
    due_now = max(due_by_today - paid, ZERO)

    next_amount, next_date, overdue, cumulative = ZERO, None, 0, ZERO
    for r in rows:
        cumulative += r.amount
        if cumulative > paid:
            if next_date is None:
                next_amount, next_date = cumulative - paid, r.due_date
            if r.due_date < today:
                overdue += 1

    return AmountsDue(
        due_now=min(due_now, outstanding),
        next_amount=min(next_amount, outstanding),
        next_due_date=next_date,
        overdue_count=overdue,
        paid=paid,
        outstanding=outstanding,
    )
