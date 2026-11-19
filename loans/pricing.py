"""
Fedha-Grow — loan pricing (single source of truth)
==================================================
Every figure a borrower is quoted or charged comes from here, so the loan
calculator, the application, the approved Loan record and the Key Facts
Statement all agree to the cent.

The CBL Financial Consumer Protection Act requires the declining-balance
(reducing-balance / EMI) method for instalment loans. Flat interest is not
permitted, and build_schedule() refuses it.

Two repayment structures:
  * instalment        declining-balance schedule, product fees included
  * single_month_end  one repayment of principal + a flat monthly fee
"""
from decimal import Decimal, ROUND_HALF_UP

from lenders.kfs_layer3_schedule import build_schedule


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def is_single_month_end(product) -> bool:
    return product is not None and getattr(product, "repayment_structure", "") == "single_month_end"


def product_fee_rows(product):
    """Product fees as the plain dicts build_schedule expects (amount Decimal)."""
    rows = []
    if product is not None:
        for f in product.fees.all():
            rows.append({
                "fee_type": f.fee_type,
                "amount": Decimal(str(f.amount)),
                "basis": f.basis,
                "applicable": f.applicable,
            })
    return rows


def quote_instalment(amount, annual_rate, term, product):
    """
    Lawful declining-balance quote, fees included — the same engine and inputs
    generate_kfs uses.

    Returns (emi, total_repayable, monthly_outflow):
      emi             : level principal + interest payment.
      total_repayable : principal + total interest + total fees (== KFS total).
      monthly_outflow : emi plus any per-instalment fee. Upfront fees land on
                        row 1, so they are in total_repayable but not here.
    """
    res = build_schedule(
        principal=amount,
        annual_rate=annual_rate,
        term_months=int(term),
        fees=product_fee_rows(product),
        interest_type="reducing",
    )
    mid = res.instalments[len(res.instalments) // 2] if res.instalments else None
    monthly_fee = mid.fees if mid is not None else Decimal("0.00")
    return res.emi, res.total_payable, money(res.emi + monthly_fee)


def quote(amount, annual_rate, term, product):
    """
    (total_repayable, monthly_payment) for any repayment structure.
    For a single month-end loan the one repayment IS the total.
    """
    amount = Decimal(str(amount))
    rate = Decimal(str(annual_rate or 0))
    if is_single_month_end(product):
        total = money(amount + amount * rate / Decimal("100"))
        return total, total
    _emi, total, monthly = quote_instalment(amount, rate, term, product)
    return total, monthly


def loan_rate(loan) -> Decimal:
    """The rate the KFS uses: the product's rate, else the loan's own rate."""
    product = getattr(loan, "product", None)
    if product is not None and product.annual_interest_rate is not None:
        return Decimal(str(product.annual_interest_rate))
    return Decimal(str(loan.interest_rate or 0))


def lawful_total(loan):
    """
    The amount this loan legally costs the borrower, and where it came from.

    Returns (total, source):
      * the Key Facts Statement total, if one exists ("kfs") — the binding
        disclosure the borrower acknowledges;
      * otherwise the declining-balance calculation ("calculated").
    """
    from loans.models import KeyFactsStatement   # avoid an import cycle

    kfs = KeyFactsStatement.objects.filter(loan_id=loan.pk).first() if loan.pk else None
    if kfs is not None and kfs.total_payable is not None:
        return money(kfs.total_payable), "kfs"
    total, _monthly = quote(loan.amount, loan_rate(loan), loan.loan_term or 1, loan.product)
    return total, "calculated"
