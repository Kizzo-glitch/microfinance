from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.db import models

#from borrowers.models import BorrowerProfile
#from lenders.models import LenderProfile
#from regulation.models import RegulatorProfile


class User(AbstractUser):
	ROLE_CHOICES = (
		('lender', 'Lender'),
		('borrower', 'Borrower'),
		('regulator', 'Regulator (CBL)'),
	)
	first_name = models.CharField(max_length=150, null=True, blank=True)
	last_name = models.CharField(max_length=150, null=True, blank=True)
	
	# 1. Expand max_length for future-proofing
	role = models.CharField(
		max_length=20, 
		choices=ROLE_CHOICES, 
		#default='borrower' # 2. Set default here instead of in save()
	)
	
	# 3. Use the existing AbstractUser email but make it unique
	email = models.EmailField(unique=True, null=True, blank=True) 
	phone_number = models.CharField(max_length=25, null=True, blank=True)
	must_change_password = models.BooleanField(default=True)

	# 4. Helper properties (keep these, they are great for templates)
	@property
	def is_lender(self):
		return self.role == 'lender'

	@property
	def is_borrower(self):
		return self.role == 'borrower'

	@property
	def is_regulator(self):
		return self.role == 'regulator'

	def save(self, *args, **kwargs):
		if not self.pk:  
			self.role = self.role 
		super().save(*args, **kwargs)
		

				
	# 5. Add a "Master Regulator" check
	# This allows you to differentiate between the Director and a regular Officer
	@property
	def is_cbl_admin(self):
		return self.is_regulator and self.is_staff

	def save(self, *args, **kwargs):
		if not self.pk:  # When creating a new user
			self.role = self.role 
		super().save(*args, **kwargs)


	def __str__(self):
		return f"{self.get_full_name() or self.username} ({self.role})"


class OTP(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE)
	phone_number = models.CharField(max_length=20)
	otp_code = models.CharField(max_length=6)
	created_at = models.DateTimeField(auto_now_add=True)
	is_verified = models.BooleanField(default=False)

	def is_expired(self):
		return timezone.now() > self.created_at + timedelta(minutes=10)  # OTP valid for 5 minutes

	def __str__(self):
		return f"{self.user.username} - {self.otp_code}"





# =====================================================================
# Payment detail fields — add to BorrowerProfile AND LenderProfile
# =====================================================================
#
# These let each party know WHERE to send money to the other:
#   * Borrower's details -> shown to the LENDER at approval, for DISBURSEMENT.
#   * Lender's details   -> shown to the BORROWER at approval, for REPAYMENT.
#
# Revealed only within an approved-loan relationship (see the reveal logic
# separately) — never in a public profile. Same field set on both models, so
# a single mixin keeps them identical.
#
# PRIVACY: account numbers are sensitive. Reveal them only to the specific
# counterparty in an approved loan, and consider masking (show last 4) in any
# list view — full details only on the specific loan's action screen.
'''
class PaymentDetailsMixin(models.Model):
    """
    Reusable payment-detail fields for a profile. Supports the two common
    Lesotho channels — a bank account and a mobile-money number — because
    people and lenders use one or the other (or both).
    """

    # --- bank ---
    bank_name            = models.CharField(max_length=100, blank=True)
    bank_account_name    = models.CharField(max_length=200, blank=True,
                              help_text="Name the account is held under.")
    bank_account_number  = models.CharField(max_length=40, blank=True)
    bank_branch_code     = models.CharField(max_length=20, blank=True)

    # --- mobile money ---
    MOBILE_MONEY_CHOICES = [
        ("", "—"),
        ("mpesa",   "M-Pesa"),
        ("ecocash", "EcoCash"),
    ]
    mobile_money_provider = models.CharField(
        max_length=20, choices=MOBILE_MONEY_CHOICES, blank=True)
    mobile_money_number   = models.CharField(max_length=20, blank=True,
                              help_text="The number money is sent to.")
    mobile_money_name     = models.CharField(max_length=200, blank=True,
                              help_text="Name registered on the mobile-money account.")

    # optional free-text instructions ("use your loan reference", etc.)
    payment_instructions  = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    # ---- helpers ----
    @property
    def has_payment_details(self) -> bool:
        return bool(
            (self.bank_account_number and self.bank_name)
            or (self.mobile_money_number and self.mobile_money_provider))

    @property
    def payment_methods_summary(self) -> str:
        """Short human summary of the methods on file (no full numbers)."""
        parts = []
        if self.bank_account_number and self.bank_name:
            parts.append(f"{self.bank_name} bank account")
        if self.mobile_money_number and self.mobile_money_provider:
            parts.append(dict(self.MOBILE_MONEY_CHOICES).get(self.mobile_money_provider, "Mobile money"))
        return " · ".join(parts) if parts else "No payment details on file"
'''








"""
Fedha-Grow — mobile money accounts (related model)
=================================================
Replaces the single mobile_money_* fields with a one-to-many model, so a person
can hold M-Pesa, EcoCash, AND C-Pay (or a future provider). Adding a new
CBL-licensed issuer is just a new choice here — no schema change to the profile.

Attaches to BOTH BorrowerProfile and LenderProfile via a generic owner, OR use
two nullable FKs — here we use a generic-ish approach with two nullable FKs so
each account belongs to exactly one profile of either type. (Kept explicit
rather than GenericForeignKey for simpler queries and admin.)

The bank account stays as flat fields on the profile (people usually have one
primary bank; banks aren't a fast-growing enumerable set like e-money issuers).
"""


class MobileMoneyAccount(models.Model):
    # Lesotho mobile-money issuers. Add a new CBL-licensed issuer as one line
    # here — no profile migration needed.
    PROVIDER_CHOICES = [
        ("mpesa",   "M-Pesa (Vodacom)"),
        ("ecocash", "EcoCash (Econet)"),
        ("cpay",    "C-Pay (Chaperone)"),
    ]

    # Each account belongs to exactly one profile (borrower OR lender).
    borrower = models.ForeignKey(
        "borrowers.BorrowerProfile", on_delete=models.CASCADE,
        null=True, blank=True, related_name="mobile_money_accounts")
    lender = models.ForeignKey(
        "lenders.LenderProfile", on_delete=models.CASCADE,
        null=True, blank=True, related_name="mobile_money_accounts")

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    number   = models.CharField(max_length=20, help_text="The number money is sent to.")
    account_name = models.CharField(max_length=200, blank=True,
                     help_text="Name registered on the mobile-money account.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # one account per provider per profile (no duplicate M-Pesa rows)
        constraints = [
            models.UniqueConstraint(
                fields=["borrower", "provider"],
                condition=models.Q(borrower__isnull=False),
                name="uniq_borrower_provider"),
            models.UniqueConstraint(
                fields=["lender", "provider"],
                condition=models.Q(lender__isnull=False),
                name="uniq_lender_provider"),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} · {self.number}"

    @property
    def owner(self):
        return self.borrower or self.lender


# =====================================================================
# The profile mixin — bank fields stay flat; mobile money is now the related set
# =====================================================================
# Replace the mobile_money_* fields in PaymentDetailsMixin with just the bank
# fields; mobile money comes from the related MobileMoneyAccount set.

class PaymentDetailsMixin(models.Model):
    """Bank fields on the profile; mobile money via related MobileMoneyAccount."""

    bank_name            = models.CharField(max_length=100, blank=True)
    bank_account_name    = models.CharField(max_length=200, blank=True,
                              help_text="Name the account is held under.")
    bank_account_number  = models.CharField(max_length=40, blank=True)
    bank_branch_code     = models.CharField(max_length=20, blank=True)

    payment_instructions = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    # ---- helpers (now aware of the related mobile-money set) ----
    @property
    def has_bank(self) -> bool:
        return bool(self.bank_account_number and self.bank_name)

    @property
    def mobile_money_list(self):
        """The profile's mobile-money accounts (queryset)."""
        return self.mobile_money_accounts.all()

    @property
    def has_mobile_money(self) -> bool:
        return self.mobile_money_accounts.exists()

    @property
    def has_payment_details(self) -> bool:
        return self.has_bank or self.has_mobile_money