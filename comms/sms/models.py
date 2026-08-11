"""
Fedha-Grow — SMS log
====================
An auditable record of every SMS the platform sends: what type, to whom, the
rendered text, and whether the provider accepted it. Python-logger output
scrolls away; this is a queryable record — useful for support ("did the
borrower get notified?") and for supervisory reconciliation.
"""

from django.db import models
from django.utils import timezone


class SmsLog(models.Model):
    STATUS_CHOICES = [
        ("sent",   "Sent"),
        ("failed", "Failed"),
    ]

    phone_number = models.CharField(max_length=20, db_index=True)
    message_type = models.CharField(max_length=64, db_index=True)
    content      = models.TextField()

    status       = models.CharField(max_length=10, choices=STATUS_CHOICES)
    provider     = models.CharField(max_length=32, default="smsportal")
    error        = models.CharField(max_length=255, blank=True)

    created_at   = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["phone_number", "message_type"])]

    def __str__(self):
        return f"{self.message_type} -> {self.phone_number} ({self.status})"