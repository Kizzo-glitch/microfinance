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



'''
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
'''

"""
Fedha-Grow — SMS service facade (with SMS_TEST_MODE)
====================================================
The single entry point for sending SMS. Renders a named message, sends it via
the configured gateway, logs to SmsLog.

TEST MODE:
  When settings.SMS_TEST_MODE is True, NO real SMS is sent. Instead the fully
  rendered message (including any activation links / OTP-style content) is:
    * written to SmsLog with status "test", AND
    * printed to the logger at INFO — which appears in Railway's log stream
      (Railway captures stdout/stderr), so you can read exactly what WOULD
      have gone out, on a fake number, without cost or texting real people.

  Turn it on for all testing:   SMS_TEST_MODE = True   (in settings / env)
  Leave it off (or unset) in production.

This protects ALL testing — invitations, activation links, OTP flows — not
just bulk import.
"""

import logging
from django.conf import settings

from .messages import render_message, UnknownMessageType
from .models import SmsLog
from .smsportal import SmsPortalGateway

logger = logging.getLogger("fedha.sms")


def _test_mode() -> bool:
    return bool(getattr(settings, "SMS_TEST_MODE", False))


def _get_gateway():
    """Resolve the SMS gateway from the integrations registry, else direct."""
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
    Render + send (or, in test mode, log) + record one SMS.

    In production: sends via the gateway, logs status sent/failed.
    In SMS_TEST_MODE: sends nothing; logs the full message to SmsLog (status
    "test") and to the logger (visible in Railway logs).
    """
    try:
        content = render_message(message_type, context or {})
    except UnknownMessageType:
        logger.error("Unknown SMS message_type: %r", message_type)
        return {"success": False, "error": f"Unknown message type: {message_type}"}

    # ---- TEST MODE: do not send; make the message visible instead ----
    if _test_mode():
        # Prominent, easy-to-grep line in Railway logs.
        logger.info(
            "\n===== SMS TEST MODE (not sent) =====\n"
            "  to:      %s\n"
            "  type:    %s\n"
            "  message: %s\n"
            "====================================",
            phone_number, message_type, content,
        )
        SmsLog.objects.create(
            phone_number=phone_number,
            message_type=message_type,
            content=content,
            status="test",
            provider="test-mode",
            error="",
        )
        return {"success": True, "test_mode": True, "content": content}

    # ---- PRODUCTION: send for real ----
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