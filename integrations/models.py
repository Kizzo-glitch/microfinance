from django.db import models
from django.utils import timezone

"""
Fedha-Grow — integrations models
================================
Records every inbound webhook so callbacks are:
  - idempotent  (a provider retrying the same event can't double-apply it)
  - auditable   (every settlement confirmation traces to a stored raw payload)
"""


class WebhookEvent(models.Model):
    """One received provider callback. De-duplicated on (provider, event_id)."""

    STATUS_CHOICES = [
        ("received",  "Received"),
        ("processed", "Processed"),
        ("duplicate", "Duplicate (ignored)"),
        ("rejected",  "Rejected (bad signature)"),
        ("error",     "Error"),
    ]

    provider   = models.CharField(max_length=64)
    event_id   = models.CharField(max_length=128, help_text="Provider's unique id for this callback.")
    reference  = models.CharField(max_length=128, blank=True, help_text="Our transaction reference, if present.")

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="received")
    signature_valid = models.BooleanField(default=False)

    raw_payload = models.JSONField(default=dict, blank=True)
    headers     = models.JSONField(default=dict, blank=True)
    note        = models.CharField(max_length=255, blank=True)

    received_at  = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                name="uniq_provider_event",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "reference"]),
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id} ({self.status})"

    def mark(self, status: str, note: str = ""):
        self.status = status
        if note:
            self.note = note[:255]
        if status == "processed":
            self.processed_at = timezone.now()
        self.save(update_fields=["status", "note", "processed_at"])

