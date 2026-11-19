
"""
Fedha-Grow — instant collection (lender side)
=============================================
Connects a lender's mobile-money account to the payment gateway so borrowers'
repayments can be collected straight into the lender's merchant account.

Flow: enable() registers the merchant with the gateway and starts a M1.00 test
payment from the lender's own number; the lender receives an OTP and
confirm() submits it. Only a verified setup is used for collection.
"""
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import CollectionSetup
from .payments.gateway import GatewayError, gateway_provider, get_gateway_client

log = logging.getLogger(__name__)


def party_ref(lender) -> str:
    return f"lender:{lender.pk}"


def _apply(setup: CollectionSetup, data: dict):
    """Mirror the gateway's view of the merchant onto the setup."""
    setup.status = data.get("status") or setup.status
    setup.last_error = (data.get("last_error") or "")[:255]
    verification = data.get("verification") or {}
    awaiting = verification.get("required_action") == "otp"
    setup.verification_expires_at = (parse_datetime(verification["expires_at"])
                                     if awaiting and verification.get("expires_at") else None)
    if setup.status == CollectionSetup.STATUS_VERIFIED and not setup.verified_at:
        setup.verified_at = timezone.now()
    if setup.status != CollectionSetup.STATUS_VERIFIED:
        setup.verified_at = None
    setup.save()


def _fail(setup, exc: GatewayError):
    setup.status = CollectionSetup.STATUS_FAILED
    setup.last_error = str(exc)[:255]
    setup.verification_expires_at = None
    setup.save()


def enable(account, *, mode, merchant_code, client_code="", client_secret=""):
    """
    Register the lender's merchant with the gateway and start verification.
    Returns (setup, test_otp). test_otp is only set by the gateway's simulator.
    Raises GatewayError if the gateway refuses the registration itself.
    """
    lender = account.lender
    provider = gateway_provider(account.provider)
    if provider is None:
        raise GatewayError("Instant collection isn't available for this provider yet.",
                           code="unsupported_provider")
    client = get_gateway_client()
    credentials = ({"client_code": client_code, "client_secret": client_secret}
                   if mode == "direct" else {})
    data = client.register_merchant(
        party_ref=party_ref(lender), provider=provider, mode=mode,
        merchant_code=merchant_code, display_name=getattr(lender, "company_name", "") or "",
        credentials=credentials)

    setup = CollectionSetup.objects.filter(account=account).first() or CollectionSetup(
        lender=lender, account=account)
    setup.provider = account.provider
    setup.mode = mode
    setup.merchant_code = merchant_code
    setup.gateway_merchant_id = data["id"]
    _apply(setup, data)

    test_otp = None
    try:
        v = client.start_verification(setup.gateway_merchant_id, msisdn=account.number)
        _apply(setup, v)
        test_otp = v.get("test_otp")
    except GatewayError as exc:
        _fail(setup, exc)
    return setup, test_otp


def resend(setup):
    """Start a fresh M1.00 verification payment (new OTP)."""
    client = get_gateway_client()
    try:
        v = client.start_verification(setup.gateway_merchant_id, msisdn=setup.account.number)
    except GatewayError as exc:
        _fail(setup, exc)
        return setup, None
    _apply(setup, v)
    return setup, v.get("test_otp")


def confirm(setup, otp):
    client = get_gateway_client()
    try:
        data = client.confirm_verification(setup.gateway_merchant_id, otp)
    except GatewayError as exc:
        _fail(setup, exc)
        return setup
    _apply(setup, data)
    return setup


def refresh(setup):
    """Pull the latest status from the gateway (e.g. after an async approval)."""
    if setup.gateway_merchant_id is None or setup.status == CollectionSetup.STATUS_DISABLED:
        return setup
    _apply(setup, get_gateway_client().get_merchant(setup.gateway_merchant_id))
    return setup


def disable(setup, reason=""):
    """Turn instant collection off here, and in the gateway once committed."""
    merchant_id = setup.gateway_merchant_id
    setup.status = CollectionSetup.STATUS_DISABLED
    setup.last_error = (reason or "")[:255]
    setup.verification_expires_at = None
    setup.verified_at = None
    setup.save()
    if merchant_id is not None:
        transaction.on_commit(lambda: _disable_on_gateway(merchant_id))
    return setup


def _disable_on_gateway(merchant_id):
    try:
        get_gateway_client().disable_merchant(merchant_id)
    except GatewayError as exc:
        # The setup is already off here, so nothing can collect through it.
        log.warning("Could not disable gateway merchant %s: %s", merchant_id, exc)


def retire_for_account(account, reason):
    """Called when a mobile-money row is deleted or its provider changes."""
    setup = CollectionSetup.objects.filter(account=account).first()
    if setup is not None and setup.status != CollectionSetup.STATUS_DISABLED:
        disable(setup, reason)
