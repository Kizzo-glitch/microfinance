"""
Fedha-Grow — USSD HTTP endpoint
===============================
Adapts the MNO/aggregator request+response format around the channel-agnostic
UssdMenuEngine. Written to the Africa's Talking shape (documented for Lesotho),
which most Southern African USSD gateways mirror:

  Inbound (POST form-encoded):
    sessionId, phoneNumber, serviceCode, text
    `text` accumulates the full keypress path, e.g. "1*2*5000" — we take the
    LAST segment as the caller's latest input.

  Outbound (plain text):
    "CON <menu>"  -> keep session open
    "END <msg>"   -> close session

GO-LIVE NOTE
  This endpoint is complete and testable today, but it is only REACHABLE by a
  real phone once an MNO (Vodacom / Econet) or an aggregator provisions a
  shortcode pointing at this URL. Until then it is "provisioned and wired,
  awaiting shortcode" — the same honest pending posture as the other
  integrations. Never describe USSD as live before a shortcode exists.
"""

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import UssdSession
from .engine import UssdMenuEngine


def _latest_input(text: str) -> str:
    """Africa's Talking sends the full path 'a*b*c'; we want the last segment."""
    if not text:
        return ""
    return text.split("*")[-1].strip()


# ---- dependency lookups injected into the engine -------------------
def _borrower_lookup(phone):
    try:
        from borrowers.models import BorrowerProfile
        return BorrowerProfile.objects.filter(phone_number=phone).first()
    except Exception:
        return None


def _lender_lookup():
    try:
        from lenders.models import LenderProfile
        return [(l.id, l.company_name) for l in LenderProfile.objects.all()[:9]]
    except Exception:
        return []


def _status_lookup(borrower):
    """Most recent application's status for this borrower, as a short label."""
    try:
        from loans.models import LoanApplication
        app = (LoanApplication.objects
               .filter(borrower=borrower, is_deleted=False)
               .order_by("-date_applied")
               .first())
        if not app:
            return None
        # Include the reference so the borrower can quote it.
        label = app.get_status_display() if hasattr(app, "get_status_display") else app.status
        ref = getattr(app, "reference_number", None)
        return f"{label} ({ref})" if ref else label
    except Exception:
        return None


def _balance_lookup(borrower):
    """Total outstanding balance across the borrower's active loans."""
    try:
        from django.db.models import Sum
        from loans.models import Loan
        total = (Loan.objects
                 .filter(borrower=borrower, outstanding_balance__gt=0)
                 .aggregate(total=Sum("outstanding_balance"))["total"])
        return total if total else None
    except Exception:
        return None


@csrf_exempt          # the gateway can't send our CSRF token; authenticate by source instead
@require_POST
def ussd_callback(request):
    session_id = request.POST.get("sessionId")
    phone = request.POST.get("phoneNumber")
    text = request.POST.get("text", "")

    if not session_id or not phone:
        return HttpResponseBadRequest("Missing sessionId or phoneNumber")

    session, _created = UssdSession.objects.get_or_create(
        session_id=session_id,
        defaults={"phone_number": phone, "state": "home"},
    )

    # First hit of a session (empty text) should always start at home.
    if not text:
        session.state = "home"
        session.save(update_fields=["state"])

    engine = UssdMenuEngine(
        borrower_lookup=_borrower_lookup,
        lender_lookup=_lender_lookup,
        status_lookup=_status_lookup,
        balance_lookup=_balance_lookup,
    )
    reply = engine.handle(session, _latest_input(text))

    # If the engine signalled a submission, hand off to the real pipeline.
    if session.context.get("submit"):
        _dispatch_application(session)
        session.remember(submit=False)  # don't double-dispatch

    if reply.end:
        session.end()

    prefix = "END" if reply.end else "CON"
    return HttpResponse(f"{prefix} {reply.text}", content_type="text/plain")


def _dispatch_application(session):
    """
    Bridge a completed USSD session into the normal loan pipeline: create a
    draft LoanApplication from the gathered context so it flows into the same
    affordability + lender-review process as an app-originated application.

    Fails safe: any error is swallowed so it never breaks the USSD response.
    """
    try:
        from loans.models import LoanApplication
        from borrowers.models import BorrowerProfile

        ctx = session.context
        borrower = BorrowerProfile.objects.filter(
            phone_number=session.phone_number
        ).first()
        if not borrower:
            return

        chosen = ctx.get("chosen_lender") or {}
        lender_id = chosen.get("id")
        if not lender_id:
            return

        # Don't create a second draft if the borrower already has one going.
        existing = LoanApplication.objects.filter(
            borrower=borrower, lender_id=lender_id, status="draft"
        ).first()
        if existing:
            application = existing
        else:
            application = LoanApplication.objects.create(
                borrower=borrower,
                lender_id=lender_id,
                loan_amount=ctx.get("amount"),
                loan_term=int(ctx.get("term") or 3),
                status="draft",
                source="ussd",               # tag the channel of origin
                current_stage="documents",   # docs/affordability come next, on the app
                status_reason="Started via USSD",
            )

        # The real reference was assigned by the model's save(); use THAT
        # everywhere (not the engine's placeholder), so USSD, the SMS, and the
        # record all cite one identifier.
        ref = application.reference_number
        session.remember(application_ref=ref)

        # Complete the USSD -> SMS handoff: tell the borrower how to finish.
        try:
            from comms.sms.service import send_sms
            send_sms(session.phone_number, "ussd_application_started", {
                "name": getattr(borrower, "full_name", "there"),
                "ref": ref,
            })
        except Exception:
            pass  # SMS failure must not break dispatch

    except Exception:
        # Never let dispatch failure break the USSD response.
        pass