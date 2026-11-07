"""
_email — hardened shared helper.

A missing template (TemplateDoesNotExist) or a flaky SMTP connection must NOT
crash the flow that sent the mail — same rule as the SMS catalogue and the
approval view: a notification is a side effect, never load-bearing. Before this,
_email("...", "emails/kfs_complete.html", ...) with no such template on disk
raised TemplateDoesNotExist and took down the KFS full-acknowledgement step.

This version:
  - renders the HTML body, catching a missing/broken template;
  - sends, catching transport errors;
  - logs every failure with the template name and recipient;
  - returns True on send, False on any failure — the caller carries on.

NOTE: written to the call site's signature
    _email(recipient, subject, template_name, context)
where `recipient` is a borrower/lender profile with .email_address (as the
approval view uses) or a plain address string. If your real _email differs,
reconcile the body — the guarding pattern is the point.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _resolve_address(recipient):
    """Accept a profile object (.email_address / .email) or a bare string."""
    if isinstance(recipient, str):
        return recipient
    return (getattr(recipient, "email_address", None)
            or getattr(recipient, "email", None))


def _email(recipient, subject, template_name, context=None) -> bool:
    """
    Send an HTML email. Never raises: logs and returns False on any failure so
    the calling flow (approval, KFS acknowledgement, etc.) is never aborted by
    a missing template or a mail-server hiccup.
    """
    to_address = _resolve_address(recipient)
    if not to_address:
        logger.warning("_email: no address for recipient=%r, template=%s — skipped",
                       recipient, template_name)
        return False

    try:
        body = render_to_string(template_name, context or {})
    except TemplateDoesNotExist:
        logger.error("_email: template %s not found — email to %s not sent",
                     template_name, to_address)
        return False
    except Exception:
        logger.exception("_email: failed rendering %s for %s", template_name, to_address)
        return False

    try:
        msg = EmailMultiAlternatives(
            subject, "", settings.EMAIL_HOST_USER, [to_address])
        msg.attach_alternative(body, "text/html")
        msg.send()
        return True
    except Exception:
        logger.exception("_email: failed sending %s to %s", template_name, to_address)
        return False