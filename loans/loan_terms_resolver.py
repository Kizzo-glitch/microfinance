"""
Single source of truth for which rate/term a loan uses.

The borrower picks a PRODUCT. From that moment the product's figures govern the
application — the lender's flat profile rate must NOT re-enter the calculation.
The profile rate/terms remain ONLY as a legacy fallback for lenders who have no
products yet.

Every view that computes a quote, affordability, or the final Loan must read
through here — so the borrower is quoted, assessed, and charged at the SAME rate
that appears on the product card and the KFS.

Put this in loans/ (or wherever shared loan helpers live) and import it widely.
"""

from decimal import Decimal
from .models import LoanApplication


def resolve_product(request, lender):
    """
    The product the borrower chose this session, or None. Validates it still
    belongs to this lender and is active — a stale/invalid session id resolves
    to None (falls back to profile) rather than trusting it blindly.
    """
    from lenders.models import LenderProduct
    pid = request.session.get("product_id")
    if not pid:
        return None
    return (LenderProduct.objects
            .filter(id=pid, lender=lender, is_active=True)
            .first())


def effective_rate(product, lender):
    """
    The annual interest rate to use. Product rate when a product is chosen,
    else the lender's profile rate (legacy lenders without products).
    Returns Decimal.
    """
    if product is not None and product.annual_interest_rate is not None:
        return Decimal(product.annual_interest_rate)
    return Decimal(lender.interest_rate or 0)


def effective_terms(product, lender):
    """
    The allowed loan terms (list of ints, months). For a product, the range
    min_term..max_term; else the lender's profile loan_terms list.

    NOTE: a single_month_end product has NO month term — it returns [] here,
    and those products must be handled by the month-end schedule path, not the
    instalment calculator. Callers should check product.repayment_structure.
    """
    if product is not None:
        if getattr(product, "repayment_structure", "installment") == "single_month_end":
            return []  # not an instalment term; handled separately
        if product.min_term and product.max_term:
            return list(range(int(product.min_term), int(product.max_term) + 1))
    return [int(t) for t in (lender.loan_terms or [])]


def effective_amount_bounds(product, lender):
    """
    (min_amount, max_amount) for validation. Product bounds if set, else
    the lender's profile min/max. Returns (Decimal|None, Decimal|None).
    """
    if product is not None and product.min_amount and product.max_amount:
        return Decimal(product.min_amount), Decimal(product.max_amount)
    return (
        Decimal(lender.min_loan_amount) if getattr(lender, "min_loan_amount", None) else None,
        Decimal(lender.max_loan_amount) if getattr(lender, "max_loan_amount", None) else None,
    )


def get_or_create_draft(request, borrower, lender, *, stage):
    """
    One place that creates/fetches the draft AND keeps its product synced to the
    session choice. Use everywhere instead of raw get_or_create.
    """
 
    loan_app, _ = LoanApplication.objects.get_or_create(
        borrower=borrower,
        lender=lender,
        status="draft",
        defaults={"current_stage": stage},
    )
    product = resolve_product(request, lender)
    if loan_app.product_id != (product.id if product else None):
        loan_app.product = product
        loan_app.save(update_fields=["product"])
    return loan_app


def approval_rate_block(loan_application, loan_amount):
    product = loan_application.product          # set during the draft flow
    lender = loan_application.lender
 
    interest = effective_rate(product, lender)  # product rate, else profile
 
    # Month-end products: flat fee, not an annualised instalment calc.
    if product is not None and getattr(product, "repayment_structure", "") == "single_month_end":
        fee = (Decimal(loan_amount) * interest / Decimal("100")).quantize(Decimal("0.01"))
        total_repayable = (Decimal(loan_amount) + fee).quantize(Decimal("0.01"))
    else:
        total_repayable = Decimal(loan_amount) * (Decimal("1") + interest / Decimal("100"))
 
    return interest, total_repayable