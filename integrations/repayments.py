"""
Fedha-Grow — borrower repayments through the payment gateway ("Pay now")
========================================================================
The borrower pays the lender's verified merchant account directly. Fedha-Grow
never holds the money; it starts the payment, relays the borrower's OTP, and
records the outcome.

Rules:
  * Amounts are worked out here (loans.schedule), never taken from the browser.
  * One payment in progress per loan.
  * A LoanPayment is created only when the gateway says the money moved, and
    only for the exact amount requested. It is confirmed automatically.
  * If the gateway can't be reached, the attempt is "being confirmed", never
    "failed" (the money may have moved). The sync job finishes it later.
"""
import logging
import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from loans.models import Loan, LoanPayment, Notification
from loans.pricing import money
from loans.schedule import amounts_due
from micro.models import MobileMoneyAccount

from .collection import party_ref
from .models import CollectionSetup, GatewayCollection
from .payments.gateway import (GatewayError, GatewayNotConfigured, gateway_provider,
                               get_gateway_client)

log = logging.getLogger(__name__)


class PayNowError(Exception):
    """A payment the borrower can't make right now; the message is for them."""


# ---------------------------------------------------------------------------
# What can this borrower do?
# ---------------------------------------------------------------------------
def instant_route(loan):
    """(setup, borrower_account) if both sides can use instant collection,
    else (None, reason): "not_connected", "lender" or "borrower"."""
    try:
        get_gateway_client()
    except GatewayNotConfigured:
        return None, "not_connected"
    setup = (CollectionSetup.objects
             .filter(lender=loan.lender, status=CollectionSetup.STATUS_VERIFIED,
                     account__isnull=False)
             .select_related("account").first())
    if setup is None or gateway_provider(setup.provider) is None:
        return None, "lender"
    account = MobileMoneyAccount.objects.filter(borrower=loan.borrower,
                                                provider=setup.provider).first()
    if account is None:
        return None, "borrower"
    return (setup, account), None


def payment_options(loan):
    """[(option, label, amount, hint)] the borrower may choose from."""
    due = amounts_due(loan)
    options = []
    if due.due_now > 0:
        hint = (f"{due.overdue_count} overdue instalment{'s' if due.overdue_count != 1 else ''}"
                if due.overdue_count else "Due today")
        options.append(("due_now", "Amount due now", due.due_now, hint))
    if due.next_amount > 0 and due.next_amount != due.due_now:
        hint = f"Due {due.next_due_date:%d %b %Y}" if due.next_due_date else ""
        options.append(("next_instalment", "Next instalment", due.next_amount, hint))
    return options


def active_collection(loan):
    for c in GatewayCollection.objects.filter(loan=loan).exclude(
            status__in=GatewayCollection.FINAL):
        if c.otp_expired:
            _close_expired(c)
        elif c.blocks_new_payment:
            return c
    return None


# ---------------------------------------------------------------------------
# Start, OTP, refresh
# ---------------------------------------------------------------------------
def start(loan, option):
    """Start an instant payment. Returns (collection, test_otp); test_otp is
    only set by the gateway's simulator."""
    amounts = {o[0]: o[2] for o in payment_options(loan)}
    if option not in amounts:
        raise PayNowError("That amount isn't available any more. Please choose again.")
    route, reason = instant_route(loan)
    if route is None:
        raise PayNowError("Instant payment isn't available for this loan. Please pay manually.")
    setup, account = route

    with transaction.atomic():
        Loan.objects.select_for_update().get(pk=loan.pk)       # one starter at a time
        if active_collection(loan) is not None:
            raise PayNowError("A payment for this loan is already in progress.")
        amount = money(amounts[option])
        if amount <= 0 or amount > money(loan.outstanding_balance or 0):
            raise PayNowError("That amount is more than you owe.")
        c = GatewayCollection.objects.create(
            loan=loan, borrower=loan.borrower, setup=setup, option=option, amount=amount,
            provider=setup.provider, payer_number=account.number,
            idempotency_key=f"fg-{uuid.uuid4().hex}")

    return _send_start(c)


def _send_start(c):
    """POST the collection. Safe to repeat: the gateway de-duplicates on our key."""
    loan = c.loan
    try:
        data = get_gateway_client().start_collection(
            source_ref=f"loan:{loan.pk}", payer_ref=f"borrower:{c.borrower_id}",
            payee_ref=party_ref(loan.lender), payer_account=c.payer_number, amount=c.amount,
            reference=c.reference, idempotency_key=c.idempotency_key,
            provider=gateway_provider(c.provider),
            narration=f"Loan {loan.reference_number or loan.pk}")
    except GatewayError as exc:
        if exc.status is not None and 400 <= exc.status < 500:
            _finish(c, GatewayCollection.STATUS_FAILED, str(exc))   # refused: nothing moved
        else:
            c.status, c.error_message = GatewayCollection.STATUS_UNKNOWN, str(exc)[:255]
            c.save()                                                # outage: finish later
        return c, None
    return _apply(c, data), data.get("test_otp")


def submit_otp(c, otp) -> GatewayCollection:
    if c.otp_expired:
        _close_expired(c)
        return c
    if c.status != GatewayCollection.STATUS_AWAITING or not c.gateway_collection_id:
        return c
    try:
        data = get_gateway_client().submit_collection_otp(c.gateway_collection_id, otp)
    except GatewayError as exc:
        if exc.status is not None and 400 <= exc.status < 500:
            c.error_message = str(exc)[:255]
            c.save(update_fields=["error_message", "updated_at"])
        else:   # we don't know if the code went through: confirm it later
            c.status, c.error_message = GatewayCollection.STATUS_UNKNOWN, str(exc)[:255]
            c.save()
        return c
    return _apply(c, data)


def refresh(c) -> GatewayCollection:
    """Ask the gateway for the latest state (used by the result page and sync job)."""
    if c.is_final:
        return c
    if c.otp_expired:
        _close_expired(c)
        return c
    if not c.gateway_collection_id:
        return _send_start(c)[0]   # the first request never got an answer: retry it
    try:
        data = get_gateway_client().get_collection(c.gateway_collection_id)
    except GatewayError as exc:
        log.warning("Could not refresh collection %s: %s", c.reference, exc)
        return c
    return _apply(c, data)


# ---------------------------------------------------------------------------
# Applying the gateway's answer
# ---------------------------------------------------------------------------
def _apply(c, data):
    with transaction.atomic():
        c = GatewayCollection.objects.select_for_update().get(pk=c.pk)
        if c.is_final:
            return c
        c.gateway_collection_id = data.get("id") or c.gateway_collection_id
        c.required_action = data.get("required_action") or ""
        c.expires_at = parse_datetime(data["expires_at"]) if data.get("expires_at") else None
        c.provider_transaction_id = data.get("provider_transaction_id") or c.provider_transaction_id
        status = data.get("status") or GatewayCollection.STATUS_UNKNOWN

        if status == GatewayCollection.STATUS_SUCCEEDED:
            if money(data.get("amount") or 0) != c.amount:
                # Never credit an amount we didn't ask for. A person must look.
                c.status = GatewayCollection.STATUS_UNKNOWN
                c.error_message = f"Gateway reported M{data.get('amount')}, expected M{c.amount}."
                c.save()
                log.error("Amount mismatch on collection %s", c.reference)
                return c
            _record_payment(c)
            return _finish(c, GatewayCollection.STATUS_SUCCEEDED, "")
        if status in (GatewayCollection.STATUS_FAILED, GatewayCollection.STATUS_CANCELLED):
            return _finish(c, GatewayCollection.STATUS_FAILED,
                           data.get("error_message") or data.get("error_code") or "Payment failed.")
        c.status = status if status in dict(GatewayCollection.STATUS_CHOICES) else c.STATUS_UNKNOWN
        c.save()
        return c


def _finish(c, status, error):
    c.status, c.error_message = status, (error or "")[:255]
    c.required_action = ""
    c.completed_at = timezone.now()
    c.save()
    return c


def _close_expired(c):
    # An expired OTP can't move money (the provider refuses it), so this attempt is over.
    _finish(c, GatewayCollection.STATUS_FAILED, "The code expired before it was entered.")


def _record_payment(c):
    """The money moved: create the LoanPayment, confirmed, and tell the lender."""
    if c.loan_payment_id:
        return
    loan = c.loan
    payment = LoanPayment.objects.create(
        borrower=c.borrower, loan=loan, amount=c.amount, flow="gateway",
        method=c.provider if c.provider in dict(LoanPayment.METHOD_CHOICES) else "gateway",
        status="claimed", external_reference=c.provider_transaction_id,
        note=f"Instant payment {c.reference}", date_paid=timezone.now())
    payment.confirm(by_lender=None)          # settles it and updates the balance
    c.loan_payment = payment
    Notification.objects.create(
        user=loan.lender.user, category="loan_payment", loan=loan,
        message=(f"{c.borrower.full_name} paid M{c.amount} for loan "
                 f"{loan.reference_number} via {c.provider_label} "
                 f"(ref {payment.reference}). Confirmed automatically."))
    Notification.objects.create(
        user=c.borrower.user, category="loan_payment", loan=loan,
        message=(f"Payment of M{c.amount} to {loan.lender.company_name} received "
                 f"(ref {payment.reference}). Thank you."))


def sync_unfinished(older_than_seconds=60):
    """For the background job: finish attempts left open (outages, closed tabs)."""
    cutoff = timezone.now() - timezone.timedelta(seconds=older_than_seconds)
    done = 0
    for c in GatewayCollection.objects.exclude(status__in=GatewayCollection.FINAL).filter(
            updated_at__lt=cutoff):
        refresh(c)
        done += 1
    return done
