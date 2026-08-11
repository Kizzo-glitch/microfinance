"""
Fedha-Grow — USSD session model
===============================
USSD is stateless: each keypress is a separate HTTP request from the MNO
gateway. This model remembers where a caller is in the menu between requests,
keyed by the gateway's session id.

Kept deliberately small and self-expiring — USSD sessions are short-lived
(typically under a couple of minutes before the network times them out).
"""

from django.db import models
from django.utils import timezone


class UssdSession(models.Model):
    session_id   = models.CharField(max_length=128, unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, db_index=True)

    # Where the caller currently is, and any data gathered this session.
    state        = models.CharField(max_length=64, default="home")
    context      = models.JSONField(default=dict, blank=True)

    created_at   = models.DateTimeField(default=timezone.now)
    updated_at   = models.DateTimeField(auto_now=True)
    ended        = models.BooleanField(default=False)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["phone_number", "ended"])]

    def __str__(self):
        return f"{self.phone_number} @ {self.state}"

    # small helpers so views stay readable
    def set_state(self, state, **ctx):
        self.state = state
        if ctx:
            self.context.update(ctx)
        self.save(update_fields=["state", "context", "updated_at"])

    def remember(self, **ctx):
        self.context.update(ctx)
        self.save(update_fields=["context", "updated_at"])

    def end(self):
        self.ended = True
        self.save(update_fields=["ended", "updated_at"])