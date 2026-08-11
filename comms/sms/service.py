"""
Fedha-Grow — SMS service facade
===============================
The single entry point the rest of the app calls to send an SMS. It renders a
named message, sends it through the configured gateway, and logs the result.

    from comms.sms.service import send_sms
    send_sms(borrower.phone_number, "loan_approved",
             {"name": borrower.full_name, "amount": amount, "lender": lender.company_name})

Views stop importing SMSPortal directly and stop hand-writing message strings.
The gateway is resolved from the integrations registry, so swapping providers
(or marking SMS connected on the status panel) is a settings change, not a
code change.
"""

import logging
from .messages import render_message, UnknownMessageType
from .models import SmsLog
from .smsportal import SmsPortalGateway

logger = logging.getLogger(__name__)


def _get_gateway():
    """
    Resolve the SMS gateway. Prefers the integrations registry (so the status
    panel and provider config stay in one place); falls back to a direct
    SMSPortal instance so SMS works even before the registry entry is added.
    """
    try:
        from integrations.registry import get_adapter
        adapter = get_adapter("sms")
        if hasattr(adapter, "send"):
            return adapter
    except Exception:  # noqa: BLE001
        pass
    return SmsPortalGateway()


def send_sms(phone_number: str, message_type: str, context: dict = None) -> dict:
    """
    Render + send + log one SMS. Never raises on send failure — returns the
    provider result dict and records an SmsLog row either way.
    """
    try:
        content = render_message(message_type, context or {})
    except UnknownMessageType:
        logger.error(f"Unknown SMS message_type: {message_type!r}")
        return {"success": False, "error": f"Unknown message type: {message_type}"}

    gateway = _get_gateway()
    result = gateway.send(phone_number, content)

    SmsLog.objects.create(
        phone_number=phone_number,
        message_type=message_type,
        content=content,
        status="sent" if result.get("success") else "failed",
        provider=getattr(gateway, "provider_name", "smsportal"),
        error=("" if result.get("success") else str(result.get("error", ""))[:255]),
    )
    return result