from django.shortcuts import render

from rest_framework import generics
from .models import Loan, Notification
from .serializers import LoanSerializer



class LoanListView(generics.ListAPIView):
	queryset = Loan.objects.all()
	serializer_class = LoanSerializer

# When the draft LoanApplication is created (in your apply flow), set the product
# from the session — alongside the lender:
#
#   product_id = request.session.get("product_id")
#   loan_app.product_id = product_id    # may be None (legacy lender w/o products)
#
# And at approval, carry it onto the Loan:
#   loan.product = loan_application.product


# =====================================================================
# D — KFS auto-generation on approve + choreography
# =====================================================================
def on_loan_approved(request, loan_application, loan):
    """
    Call this from the approval flow, right AFTER the Loan is created.
    Auto-generates the KFS, sets disbursement status, notifies the borrower.
    Returns the KFS (or None if it couldn't be generated).
    """
    # from comms.sms.service import send_sms

    # carry the product from application onto the loan (if not already)
    if getattr(loan_application, "product_id", None) and not getattr(loan, "product_id", None):
        loan.product = loan_application.product
        loan.save(update_fields=["product"])

    kfs = None
    # KFS needs a product (for fees) — only auto-generate when one is attached.
    if getattr(loan, "product_id", None):
        kfs = generate_kfs(loan)

    # disbursement status: can't disburse until the borrower acknowledges the KFS
    if hasattr(loan, "disbursement_status"):
        loan.disbursement_status = "pending_kfs" if kfs else "ready"  # no KFS req'd if no product (legacy)
        loan.save(update_fields=["disbursement_status"])

    # notify the borrower — they have a statement to review
    borrower_user = getattr(loan.borrower, "user", None)
    if borrower_user and kfs:
        Notification.objects.create(
            user=borrower_user, category="loan_approved",
            message=(f"Your loan from {loan.lender.company_name} is approved. "
                     f"Please review and acknowledge your Key Facts Statement "
                     f"({kfs.reference}) before it is disbursed."),
            loan=loan)
        # send_sms(loan.borrower.phone_number, "loan_approved_kfs",
        #          {"name": loan.borrower.full_name, "lender": loan.lender.company_name,
        #           "ref": kfs.reference, "url": request.build_absolute_uri(...)})

    return kfs

# =====================================================================
# Generation — assemble the frozen snapshot from the approved loan
# =====================================================================
def generate_kfs(loan, *, product=None):
    """
    Build (or return existing) the immutable KFS for an approved loan.
    Freezes provider details, product terms, fees, schedule and totals into
    the snapshot JSON. Idempotent: won't regenerate if one already exists.
    """
    existing = getattr(loan, "kfs", None)
    if existing:
        return existing

    lender = loan.lender
    borrower = loan.borrower
    product = product or _resolve_product(loan)

    # fees as plain dicts for the schedule builder + the snapshot
    fee_rows = []
    if product:
        for f in product.fees.all():
            fee_rows.append({
                "fee_type": f.fee_type, "label": f.get_fee_type_display(),
                "amount": str(f.amount), "basis": f.basis,
                "basis_label": f.get_basis_display(),
                "applicable": f.applicable, "note": f.note,
            })

    annual_rate = product.annual_interest_rate if product else loan.interest_rate
    term = loan.loan_term
    interest_type = product.interest_type if product else "flat"

    cb = build_schedule(
        principal=loan.amount, annual_rate=annual_rate, term_months=term,
        fees=[{**fr, "amount": Decimal(fr["amount"])} for fr in fee_rows],
        interest_type=interest_type)

    snapshot = {
        "provider": {
            "name": lender.company_name,
            "registered_name": getattr(lender, "registered_name", "") or lender.company_name,
            "cbl_licence_number": getattr(lender, "cbl_licence_number", ""),
            "registered_address": getattr(lender, "registered_address", ""),
            "service_phone": getattr(lender, "service_phone", ""),
            "service_email": getattr(lender, "service_email", ""),
            "complaints_phone": getattr(lender, "complaints_phone", ""),
            "complaints_email": getattr(lender, "complaints_email", ""),
        },
        "borrower": {
            "full_name": borrower.full_name,
            "id_number_masked": _mask(getattr(borrower, "id_number", "")),
            "mobile_masked": _mask(getattr(borrower, "phone_number", "")),
        },
        "product": {
            "name": product.name if product else "",
            "code": product.product_code if product else "",
            "version": product.version if product else "",
            "interest_type": interest_type,
            "interest_calculation_note": getattr(product, "interest_calculation_note", "") if product else "",
            "repayment_frequency": product.get_repayment_frequency_display() if product else "Monthly",
        },
        "terms": {
            "approved_amount": str(loan.amount),
            "term_months": term,
            "annual_interest_rate": str(annual_rate),
            "monthly_interest_rate": str((Decimal(str(annual_rate)) / 12).quantize(Decimal("0.01"))),
        },
        "fees": fee_rows,
        "cost": {
            "principal": str(cb.principal),
            "total_interest": str(cb.total_interest),
            "total_fees": str(cb.total_fees),
            "fees_by_type": {k: str(v) for k, v in cb.fees_by_type.items()},
            "total_payable": str(cb.total_payable),
        },
        "schedule": [
            {"number": i.number, "principal": str(i.principal), "interest": str(i.interest),
             "fees": str(i.fees), "total": str(i.total), "balance": str(i.balance)}
            for i in cb.instalments
        ],
    }

    kfs = KeyFactsStatement.objects.create(
        loan=loan, loan_application=getattr(loan, "application_source", None),
        snapshot=snapshot, approved_amount=loan.amount,
        total_payable=cb.total_payable,
        product_code=product.product_code if product else "",
    )
    return kfs

def _resolve_product(loan):
    """Which product this loan was issued under. Adjust to your linkage."""
    return getattr(loan, "product", None)


def _mask(value: str) -> str:
    """Mask all but the last 4 chars for display (ID, phone)."""
    s = str(value or "")
    if len(s) <= 4:
        return s
    return "•" * (len(s) - 4) + s[-4:]