from django.shortcuts import render
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist

from comms.sms.service import send_sms
from lenders.kfs_layer3_schedule import build_month_end_schedule, build_schedule
from micro.views import notify_borrower_kfs_ready
from rest_framework import generics
from .models import KeyFactsStatement, Loan, Notification
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
    #notify_borrower_kfs_ready(loan, kfs) 
    # KFS needs a product (for fees) — only auto-generate when one is attached.
    if getattr(loan, "product_id", None):
        kfs = generate_kfs(loan)

    if kfs is not None:
        notify_borrower_kfs_ready(loan, kfs)

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
        send_sms(loan.borrower.phone_number, "loan_approved_kfs",
                  {"name": loan.borrower.full_name, "lender": loan.lender.company_name,
                   "ref": kfs.reference, "url": request.build_absolute_uri(...)})

    return kfs

def _verified_licence_number(lender):
    """
    The CBL licence number ONLY if verified — else "". Reads the authoritative
    field on the ComplianceProfile (lender.compliance), the same source the
    profile/product-list/borrower-detail use. Never shows an unverified claim.
    """
    try:
        cp = lender.compliance            # reverse OneToOne -> may raise
    except ObjectDoesNotExist:
        return ""
    if cp and cp.license_verification_state == "verified":
        return cp.cbl_license_number or ""
    return ""

# =====================================================================
# Generation — assemble the frozen snapshot from the approved loan
# =====================================================================
"""
generate_kfs — corrected.

Three things the previous version got wrong:

 1. single_month_end products were never handled. generate_kfs always called
    build_schedule(..., interest_type=...). A month-end product's interest_type
    is 'flat' -> build_schedule RAISES -> KFS generation crashed for that whole
    product line. Now it branches on product.repayment_structure and calls
    build_month_end_schedule for single-repayment products.

 2. The two builders return DIFFERENT shapes — build_schedule -> ScheduleResult
    (attributes: cb.principal, cb.instalments, i.principal), build_month_end_schedule
    -> dict (keys: cb["principal"], i["amount"]). The snapshot only read the
    ScheduleResult shape. A normalizer now flattens EITHER into the same
    snapshot cost/schedule keys the template consumes (data.cost.*, data.schedule).

 3. interest_type fell back to 'flat' when no product was attached, which
    build_schedule refuses. Flat is unlawful anyway, so the no-product fallback
    is 'reducing'.

The provider block keeps the verified-licence fix (_verified_licence_number).
"""



def _schedule_for_snapshot(loan, product, annual_rate, term, fee_rows):
    """
    Run the right builder for the product's repayment structure and return a
    SINGLE flat shape the snapshot uses, regardless of which builder ran:

        {
          "cost": {principal, total_interest, total_fees, fees_by_type,
                   total_payable},
          "schedule": [ {number, principal, interest, fees, total, balance}, ... ],
          "total_payable": Decimal,   # for the promoted KeyFactsStatement field
        }

    Instalment (declining-balance) and single-month-end are the two structures.
    """
    structure = getattr(product, "repayment_structure", "instalment") if product else "instalment"

    if structure == "single_month_end":
        # One lump repayment + flat fee. Needs a disbursement date for the
        # month-end due date: prefer a date already on the loan, else today.
        disbursement_date = (
            getattr(loan, "disbursement_date", None)
            or getattr(loan, "start_date", None)
            or timezone.now().date()
        )
        md = build_month_end_schedule(loan.amount, product, disbursement_date)

        # Month-end has no instalment interest; the "interest" line is the flat
        # fee, and fees_by_type is empty (the fee IS the charge, shown as interest).
        cost = {
            "principal": str(md["principal"]),
            "total_interest": str(md["total_interest"]),   # the flat monthly fee
            "total_fees": str(md["total_fees"]),           # 0.00
            "fees_by_type": {},
            "total_payable": str(md["total_payable"]),
        }
        schedule = [{
            "number": row["number"],
            "principal": str(row["principal"]),
            "interest": str(row["interest"]),
            "fees": str(row["fees"]),
            "total": str(row["total"]),
            # month-end uses balance_after; normalize to the 'balance' key
            "balance": str(row.get("balance", row.get("balance_after", Decimal("0.00")))),
        } for row in md["instalments"]]

        return {
            "cost": cost,
            "schedule": schedule,
            "total_payable": md["total_payable"],
            "interest_note": md.get("interest_note", ""),
        }

    # ── instalment (declining-balance) ──────────────────────────────────────
    cb = build_schedule(
        principal=loan.amount,
        annual_rate=annual_rate,
        term_months=term,
        fees=[{**fr, "amount": Decimal(fr["amount"])} for fr in fee_rows],
        interest_type="reducing",      # lawful path only; 'flat' would raise
    )

    cost = {
        "principal": str(cb.principal),
        "total_interest": str(cb.total_interest),
        "total_fees": str(cb.total_fees),
        "fees_by_type": {k: str(v) for k, v in cb.fees_by_type.items()},
        "total_payable": str(cb.total_payable),
    }
    schedule = [{
        "number": i.number,
        "principal": str(i.principal),
        "interest": str(i.interest),
        "fees": str(i.fees),
        "total": str(i.total),
        "balance": str(i.balance),
    } for i in cb.instalments]

    return {
        "cost": cost,
        "schedule": schedule,
        "total_payable": cb.total_payable,
        "interest_note": "",
    }


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
    # Disclosed interest_type: the product's own label (what the borrower sees).
    # Flat is unlawful for instalment loans — the schedule builder enforces that;
    # here we only record what the product claims, and never pass 'flat' on.
    interest_type = product.interest_type if product else "reducing"

    # Run the correct builder for the structure and flatten to snapshot shape.
    sched = _schedule_for_snapshot(loan, product, annual_rate, term, fee_rows)

    snapshot = {
        "provider": {
            "name": lender.company_name,
            "registered_name": getattr(lender, "registered_name", "") or lender.company_name,
            "cbl_licence_number": _verified_licence_number(lender),
            "registered_address": getattr(lender, "business_address", "") or getattr(lender, "physical_address", ""),
            "service_phone": getattr(lender, "phone_number", ""),
            "service_email": getattr(lender, "business_email", ""),
            "complaints_phone": getattr(lender, "phone_number", ""),
            "complaints_email": getattr(lender, "complaints_email", "")
                                or getattr(lender, "business_email", ""),
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
            "interest_calculation_note": (
                getattr(product, "interest_calculation_note", "") if product else ""
            ) or sched["interest_note"],
            "repayment_frequency": product.get_repayment_frequency_display() if product else "Monthly",
            "repayment_structure": getattr(product, "repayment_structure", "instalment") if product else "instalment",
        },
        "terms": {
            "approved_amount": str(loan.amount),
            "term_months": term,
            "annual_interest_rate": str(annual_rate),
            "monthly_interest_rate": str(
                (Decimal(str(annual_rate)) / Decimal("12")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)),
        },
        "fees": fee_rows,
        "cost": sched["cost"],
        "schedule": sched["schedule"],
    }

    kfs = KeyFactsStatement.objects.create(
        loan=loan,
        loan_application=getattr(loan, "application_source", None),
        snapshot=snapshot,
        approved_amount=loan.amount,
        total_payable=sched["total_payable"],
        product_code=product.product_code if product else "",
    )
    return kfs

'''
def generate_kfs(loan, *, product=None):
    
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
            
            "cbl_licence_number": _verified_licence_number(lender),
            
            "registered_address": getattr(lender, "business_address", "") or getattr(lender, "physical_address", ""),
            "service_phone": getattr(lender, "phone_number", ""),
            "service_email": getattr(lender, "business_email", ""),
            "complaints_phone": getattr(lender, "phone_number", ""),
            "complaints_email": getattr(lender, "complaints_email", "")
                                or getattr(lender, "business_email", ""),
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
    return kfs'''

def _resolve_product(loan):
    """Which product this loan was issued under. Adjust to your linkage."""
    return getattr(loan, "product", None)


def _mask(value: str) -> str:
    """Mask all but the last 4 chars for display (ID, phone)."""
    s = str(value or "")
    if len(s) <= 4:
        return s
    return "•" * (len(s) - 4) + s[-4:]

