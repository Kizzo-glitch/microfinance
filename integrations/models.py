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




class CollectionSetup(models.Model):
    """
    A lender's "instant collection" on one mobile-money account: borrowers'
    repayments are collected straight into the lender's merchant account
    through the payment gateway, and confirmed automatically.

    Lives here, not on MobileMoneyAccount, because only lenders have it and it
    has its own lifecycle. Credentials are NOT stored in Fedha-Grow: they go
    straight to the gateway. Only the gateway's merchant id is kept.
    """

    STATUS_PENDING = "pending_verification"
    STATUS_VERIFIED = "verified"
    STATUS_FAILED = "failed"
    STATUS_DISABLED = "disabled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Waiting for verification"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_FAILED, "Verification failed"),
        (STATUS_DISABLED, "Disabled"),
    ]
    MODE_CHOICES = [
        ("direct", "My own merchant account"),
        ("sub_merchant", "Set up through Fedha-Grow"),
    ]

    lender = models.ForeignKey("lenders.LenderProfile", on_delete=models.CASCADE,
                               related_name="collection_setups")
    account = models.OneToOneField("micro.MobileMoneyAccount", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="collection_setup",
                                   help_text="Cleared if the account is deleted (the record is kept).")
    provider = models.CharField(max_length=20, help_text="Fedha-Grow provider code, e.g. cpay.")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="direct")
    merchant_code = models.CharField(max_length=64)
    gateway_merchant_id = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    last_error = models.CharField(max_length=255, blank=True)
    verification_expires_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lender} · {self.provider} {self.merchant_code} ({self.status})"

    @property
    def is_verified(self):
        return self.status == self.STATUS_VERIFIED

    @property
    def awaiting_otp(self):
        return self.status == self.STATUS_PENDING and self.verification_expires_at is not None


class GatewayCollection(models.Model):
    """
    One attempt by a borrower to pay instantly through the payment gateway.

    Failed or abandoned attempts stay here and never reach the borrower's
    payment history: a LoanPayment is created ONLY when the gateway reports the
    money has moved (and is then confirmed automatically).
    """

    STATUS_CREATED = "created"
    STATUS_PENDING = "pending"
    STATUS_AWAITING = "awaiting_action"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Starting"),
        (STATUS_PENDING, "Processing"),
        (STATUS_AWAITING, "Waiting for the borrower's code"),
        (STATUS_SUCCEEDED, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_UNKNOWN, "Being confirmed"),
    ]
    FINAL = {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELLED}

    OPTION_CHOICES = [("due_now", "Amount due now"), ("next_instalment", "Next instalment")]

    loan = models.ForeignKey("loans.Loan", on_delete=models.PROTECT, related_name="gateway_collections")
    borrower = models.ForeignKey("borrowers.BorrowerProfile", on_delete=models.PROTECT,
                                 related_name="gateway_collections")
    setup = models.ForeignKey(CollectionSetup, on_delete=models.PROTECT, related_name="collections")
    option = models.CharField(max_length=20, choices=OPTION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider = models.CharField(max_length=20, help_text="Fedha-Grow provider code, e.g. cpay.")
    payer_number = models.CharField(max_length=20)
    reference = models.CharField(max_length=24, unique=True, editable=False, null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    gateway_collection_id = models.CharField(max_length=64, blank=True, db_index=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)
    required_action = models.CharField(max_length=24, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    provider_transaction_id = models.CharField(max_length=128, blank=True)
    error_message = models.CharField(max_length=255, blank=True)

    loan_payment = models.OneToOneField("loans.LoanPayment", null=True, blank=True,
                                        on_delete=models.PROTECT, related_name="gateway_collection")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} M{self.amount} loan {self.loan_id} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            from loans.references import generate_reference
            self.reference = generate_reference(GatewayCollection, "reference", prefix="FGC")
        super().save(*args, **kwargs)

    @property
    def is_final(self):
        return self.status in self.FINAL

    @property
    def provider_label(self):
        from micro.models import MobileMoneyAccount
        label = dict(MobileMoneyAccount.PROVIDER_CHOICES).get(self.provider, self.provider)
        return label.split(" (")[0]          # "C-Pay (Chaperone)" -> "C-Pay"

    @property
    def otp_expired(self):
        return (self.status == self.STATUS_AWAITING and self.expires_at is not None
                and self.expires_at <= timezone.now())

    @property
    def blocks_new_payment(self):
        """Only one payment in progress per loan. An OTP that has expired can no
        longer move money, so it doesn't block a new attempt."""
        return not self.is_final and not self.otp_expired
