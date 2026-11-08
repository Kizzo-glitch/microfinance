from django.shortcuts import render
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from django.urls import reverse

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from comms.sms.service import send_sms
from lenders.kfs_layer3_schedule import build_month_end_schedule, build_schedule

from loans.email_helper_hardened import _email
from loans.email_helper_hardened import _email
from rest_framework import generics
from .models import KeyFactsStatement, Loan, Notification
from .serializers import LoanSerializer



class LoanListView(generics.ListAPIView):
	queryset = Loan.objects.all()
	serializer_class = LoanSerializer



# =====================================================================
# D — KFS auto-generation on approve + choreography
# =====================================================================

 
def _approve_loan_db(loan_application, loan):
    """
    DB-only post-approval work. Safe to run inside transaction.atomic().
    Returns the generated KFS, or None when no product is attached (legacy).
    """
    # Carry the product from application onto the loan if not already set.
    if getattr(loan_application, "product_id", None) and not getattr(loan, "product_id", None):
        loan.product = loan_application.product
        loan.save(update_fields=["product"])
 
    kfs = None
    # KFS needs a product (for fees) — only auto-generate when one is attached.
    if getattr(loan, "product_id", None):
        kfs = generate_kfs(loan)
 
    # Disbursement gate: can't disburse until the borrower acknowledges the KFS.
    if hasattr(loan, "disbursement_status"):
        loan.disbursement_status = "pending_kfs" if kfs else "ready"
        loan.save(update_fields=["disbursement_status"])
 
    return kfs
 
 
def on_loan_approved_notify(request, loan, kfs):
    """
    Borrower-facing notification + SMS for an approved loan with a KFS.
    Run AFTER the approval transaction commits. Does no approval-critical DB
    work, so a gateway failure here never rolls back the approval.
    """
    if kfs is None:
        return
 
    notify_borrower_kfs_ready(loan, kfs)
 
    borrower_user = getattr(loan.borrower, "user", None)
    if borrower_user:
        Notification.objects.create(
            user=borrower_user, category="loan_approved",
            message=(f"Your loan from {loan.lender.company_name} is approved. "
                     f"Please review and acknowledge your Key Facts Statement "
                     f"({kfs.reference}) before it is disbursed."),
            loan=loan)
 
        # THE FIX: real acknowledgement URL instead of the `...` placeholder
        # that raised TypeError in build_absolute_uri and aborted the redirect.
        kfs_url = request.build_absolute_uri(
            reverse("loans:view_kfs", args=[kfs.pk]))
 
        send_sms(loan.borrower.phone_number, "loan_approved_kfs", {
            "name": loan.borrower.full_name,
            "lender": loan.lender.company_name,
            "ref": kfs.reference,
            "url": kfs_url,
        })


'''
def on_loan_approved(request, loan_application, loan):
    """
    Call this from the approval flow, right AFTER the Loan is created.
    Auto-generates the KFS, sets disbursement status, notifies the borrower.
    Returns the KFS (or None if it couldn't be generated).
    """


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

    return kfs'''

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



def _resolve_product(loan):
    """Which product this loan was issued under. Adjust to your linkage."""
    return getattr(loan, "product", None)


def _mask(value: str) -> str:
    """Mask all but the last 4 chars for display (ID, phone)."""
    s = str(value or "")
    if len(s) <= 4:
        return s
    return "•" * (len(s) - 4) + s[-4:]




#++++++++++++++++++++++++++++++++++
# New kfs
#==================================
"""
KFS views — FINAL, against the real KeyFactsStatement (status-machine model
with on-model ack-record fields + record_borrower_ack / record_lender_ack).

The model methods enforce order and single-signing, so the view just:
  resolves the viewer -> calls the right record_* method -> notifies.
No field guessing left.
"""

@login_required
def view_kfs(request, kfs_id):
    #from loans.models import KeyFactsStatement
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)

    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    # Borrower-first ordering, read straight off the status machine.
    can_borrower_sign = role == "borrower" and kfs.status == "generated"
    can_lender_sign = role == "lender" and kfs.status == "borrower_ack"

    return render(request, "kfs_document.html", {
        "kfs": kfs,
        "snapshot": kfs.snapshot,
        "data": kfs.snapshot, 
        "loan": loan,
        "borrower": borrower,
        "lender": lender,
        "role": role,
        "can_borrower_sign": can_borrower_sign,
        "can_lender_sign": can_lender_sign,
        "fully_acknowledged": kfs.status == "acknowledged",
    })



@login_required
def acknowledge_kfs(request, kfs_id):
    if request.method != "POST":
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)
    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    typed_name = (request.POST.get("typed_name") or "").strip()
    if not typed_name:
        messages.error(request, "Please type your full name to acknowledge.")
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    if role == "borrower":
        ok = kfs.record_borrower_ack(user=request.user, typed_name=typed_name)
        if not ok:
            messages.info(request, "This statement can't be acknowledged again.")
        else:
            notify_lender_of_borrower_ack(loan, kfs)
            messages.success(request, "Thank you — your acknowledgement is recorded. "
                                      "The lender will confirm before disbursement.")
    else:  # lender
        ok = kfs.record_lender_ack(user=request.user, typed_name=typed_name)
        if not ok:
            # record_lender_ack returns False if borrower hasn't gone first,
            # or it's already confirmed/locked.
            if kfs.status == "generated":
                messages.error(request, "The borrower must acknowledge first.")
            else:
                messages.info(request, "This statement is already confirmed.")
        else:
            notify_borrower_fully_acknowledged(loan, kfs)
            messages.success(request, "Confirmed. Both parties have acknowledged "
                                      "the Key Facts Statement.")

    return redirect("loans:view_kfs", kfs_id=kfs_id)


def _viewer_role(user, borrower, lender):
    if getattr(borrower, "user", None) == user:
        return "borrower"
    if getattr(lender, "user", None) == user:
        return "lender"
    return None   # staff removed — only the actual parties sign (CBL-tight)



"""
KFS notifications — in-app + SMS + email, at each step of the acknowledgement flow.

Three triggers:
  1. KFS generated (on approval)         -> notify BORROWER to review & acknowledge
  2. Borrower acknowledged               -> notify LENDER to confirm
  3. Both acknowledged (lender confirmed)-> notify BORROWER it's complete

Reuses what you already have: Notification model, send_sms (honours
SMS_TEST_MODE), EmailMultiAlternatives. Each channel is wrapped so one failing
(e.g. no email on file) never blocks the others or the acknowledgement itself.
"""

def _kfs_url(request_or_none, kfs):
    """Absolute-ish path to the KFS view. Pass request to make it absolute."""
    path = reverse("loans:view_kfs", kwargs={"kfs_id": kfs.pk})
    return path  # templates/SMS can prefix with the site domain if needed.


# ── Trigger 1: KFS generated -> borrower, please review & acknowledge ──────

def notify_borrower_kfs_ready(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"Your Key Facts Statement for the M{loan.amount} loan from "
           f"{lender.company_name} is ready. Please review and acknowledge it "
           f"before the loan can be disbursed.")

    _in_app(borrower.user, msg, "kfs_ready", kfs.loan_application)
    _sms(borrower, "kfs_ready", {
        "name": borrower.full_name, "amount": loan.amount,
        "lender": lender.company_name, "ref": getattr(kfs, "reference", ""),
    })
    _email(borrower, "Your Key Facts Statement is ready", "kfs_ready.html", {
        "borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs,
    })


# ── Trigger 2: borrower acknowledged -> lender, please confirm ─────────────

def notify_lender_of_borrower_ack(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{borrower.full_name} has acknowledged the Key Facts Statement for "
           f"their M{loan.amount} loan. Please confirm to proceed to disbursement.")

    _in_app(lender.user, msg, "kfs_borrower_acknowledged", kfs.loan_application)
    _sms(lender, "kfs_borrower_acknowledged", {
        "borrower": borrower.full_name, "amount": loan.amount,
        "ref": getattr(kfs, "reference", ""),
    })
    _email(lender, "Borrower acknowledged the Key Facts Statement",
           "kfs_borrower_ack.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})


# ── Trigger 3: both acknowledged -> borrower, it's complete ────────────────

def notify_borrower_fully_acknowledged(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{lender.company_name} has confirmed your Key Facts Statement. "
           f"Both parties have now acknowledged it.")

    _in_app(borrower.user, msg, "kfs_complete", kfs.loan_application)
    _sms(borrower, "kfs_complete", {
        "name": borrower.full_name, "lender": lender.company_name,
        "ref": getattr(kfs, "reference", ""),
    })
    _email(borrower, "Key Facts Statement acknowledged by both parties",
           "kfs_complete.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})



# ---------------------------------------------------------------------------
# channel helpers — each isolated so a failure can't block the others
# ---------------------------------------------------------------------------

def _in_app(user, message, category, loan_application=None):
    try:
        from loans.models import Notification       
        Notification.objects.create(
            user=user, message=message, category=category,
            loan_application=loan_application,
        )
    except Exception:
        pass


def _sms(profile, template_key, context):
    try:
                         
        phone = getattr(profile, "phone_number", None)
        if phone:
            send_sms(phone, template_key, context)         
    except Exception:
        pass

''''
def _email(profile, subject, template, context):
    try:
        to = getattr(profile, "email_address", None) or getattr(
            getattr(profile, "user", None), "email", None)
        if not to:
            return
        body = render_to_string(template, context)
        email = EmailMultiAlternatives(subject, "", settings.EMAIL_HOST_USER, [to])
        email.attach_alternative(body, "text/html")
        email.send()
    except Exception:
        pass'''




'''
@login_required
def view_kfs(request, kfs_id):
    from loans.models import KeyFactsStatement
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)

    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    # Borrower-first ordering, read straight off the status machine.
    can_borrower_sign = role == "borrower" and kfs.status == "generated"
    can_lender_sign = role == "lender" and kfs.status == "borrower_ack"

    print("KFS DEBUG — context keys going to template:", list({
    "kfs": kfs, "data": kfs.snapshot}.keys()))
    print("KFS DEBUG — data has provider?:", "provider" in (kfs.snapshot or {}))

    return render(request, "kfs_document.html", {
        "kfs": kfs,
        "snapshot": kfs.snapshot,
        "data": kfs.snapshot,
        "loan": loan,
        "borrower": borrower,
        "lender": lender,
        "role": role,
        "can_borrower_sign": can_borrower_sign,
        "can_lender_sign": can_lender_sign,
        "fully_acknowledged": kfs.status == "acknowledged",
    })



@login_required
def acknowledge_kfs(request, kfs_id):
    if request.method != "POST":
        return redirect("view_kfs", kfs_id=kfs_id)


   
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)
    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    typed_name = (request.POST.get("typed_name") or "").strip()
    if not typed_name:
        messages.error(request, "Please type your full name to acknowledge.")
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    if role == "borrower":
        ok = kfs.record_borrower_ack(user=request.user, typed_name=typed_name)
        if not ok:
            messages.info(request, "This statement can't be acknowledged again.")
        else:
            notify_lender_of_borrower_ack(loan, kfs)
            messages.success(request, "Thank you — your acknowledgement is recorded. "
                                      "The lender will confirm before disbursement.")
    else:  # lender
        ok = kfs.record_lender_ack(user=request.user, typed_name=typed_name)
        if not ok:
            # record_lender_ack returns False if borrower hasn't gone first,
            # or it's already confirmed/locked.
            if kfs.status == "generated":
                messages.error(request, "The borrower must acknowledge first.")
            else:
                messages.info(request, "This statement is already confirmed.")
        else:
            notify_borrower_fully_acknowledged(loan, kfs)
            messages.success(request, "Confirmed. Both parties have acknowledged "
                                      "the Key Facts Statement.")

    return redirect("view_kfs", kfs_id=kfs_id)'''

