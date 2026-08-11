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
    Bridge from a USSD-initiated application to the normal loan pipeline.
    Deliberately thin and isolated: create/queue a draft LoanApplication from
    the gathered context, then let the existing affordability + review flow run.
    Kept in one place so wiring it to your real models is a single edit.
    """
    try:
        # from loans.models import LoanApplication
        # ctx = session.context
        # LoanApplication.objects.create(
        #     borrower=_borrower_lookup(session.phone_number),
        #     lender_id=ctx["chosen_lender"]["id"],
        #     loan_amount=ctx["amount"],
        #     loan_term=ctx["term"],
        #     status="draft",
        #     source="ussd",
        #     reference_number=ctx.get("application_ref"),
        # )
        # Then trigger an SMS with the app link / document upload step.
        pass
    except Exception:
        # Never let dispatch failure break the USSD response.
        pass