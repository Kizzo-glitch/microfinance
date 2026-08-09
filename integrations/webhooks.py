"""
Fedha-Grow — webhook receiver
=============================
Single hardened entry point for provider callbacks. Every payment provider
posts here at /integrations/webhooks/<category>/.

The order of checks is the security-critical part:
  1. resolve the category -> adapter (unknown category = 404)
  2. verify the signature via the adapter (bad signature = 401, logged)
  3. extract a stable event id; de-duplicate (retry = 200, no re-apply)
  4. parse + apply exactly once; store the raw payload for audit

A pending provider's adapter rejects all signatures, so no callback can be
processed until a real provider is connected. That's intentional.
"""

import json
from django.http import JsonResponse, Http404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .registry import get_adapter, _PAYMENT_CATEGORIES
from .base import PaymentStatus
from .models import WebhookEvent


def _headers_dict(request) -> dict:
    return {k: v for k, v in request.headers.items()}


@csrf_exempt          # providers can't send our CSRF token; we authenticate by signature instead
@require_POST
def payment_webhook(request, category: str):
    # 1. category must be a real payment category
    if category not in _PAYMENT_CATEGORIES:
        raise Http404("Unknown webhook category")

    adapter = get_adapter(category)

    # 2. authenticity: only the real provider's signed calls proceed
    if not adapter.verify_webhook_signature(request):
        WebhookEvent.objects.create(
            provider=getattr(adapter, "provider_name", category),
            event_id=f"unsigned-{timezone.now().timestamp()}",
            status="rejected",
            signature_valid=False,
            headers=_headers_dict(request),
            note="Signature verification failed or provider not connected.",
        )
        return JsonResponse({"detail": "invalid signature"}, status=401)

    # 3. parse the authenticated payload
    result = adapter.parse_webhook(request)
    try:
        raw = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        raw = {}

    event_id = result.data.get("event_id") or result.reference

    # idempotency: the same event arriving twice is stored once, applied once
    event, created = WebhookEvent.objects.get_or_create(
        provider=result.provider,
        event_id=event_id,
        defaults={
            "reference": result.reference,
            "signature_valid": True,
            "raw_payload": raw,
            "headers": _headers_dict(request),
            "status": "received",
        },
    )
    if not created:
        event.mark("duplicate", "Repeat delivery ignored.")
        return JsonResponse({"detail": "duplicate ignored", "reference": event.reference}, status=200)

    # 4. apply exactly once
    try:
        _apply_payment_result(result)
        event.mark("processed")
    except Exception as exc:  # noqa: BLE001 — record, don't crash the callback
        event.mark("error", f"{type(exc).__name__}: {exc}")
        return JsonResponse({"detail": "processing error"}, status=500)

    return JsonResponse({
        "detail": "ok",
        "status": result.status.value,
        "reference": result.reference,
    }, status=200)


def _apply_payment_result(result):
    """
    Reconcile a confirmed settlement against our own transaction record.

    Deliberately thin for now: when the loan/disbursement transaction model is
    wired to references, this looks up that record and marks it confirmed.
    Kept isolated so going live touches ONE function.
    """
    if result.status != PaymentStatus.CONFIRMED:
        return
    # from loans.models import Disbursement
    # txn = Disbursement.objects.filter(reference=result.reference).first()
    # if txn:
    #     txn.mark_confirmed(amount=result.amount, source=result.provider)
    return