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

from django.db import models


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


# =====================================================================
# How to apply (two options)
# =====================================================================
#
# OPTION A — inherit the mixin (cleanest; identical fields on both):
#
#   class BorrowerProfile(PaymentDetailsMixin, models.Model):
#       ...existing fields...
#
#   class LenderProfile(PaymentDetailsMixin, models.Model):
#       ...existing fields...
#
#   (Mixin must be BEFORE models.Model in the inheritance list. Because the
#   mixin is abstract, its fields are added to each concrete model. Run
#   makemigrations after.)
#
# OPTION B — if you can't change the base classes easily, paste the field
# block (bank_* , mobile_money_* , payment_instructions) directly into each
# model. Identical result, more duplication.
#
# Either way: makemigrations + migrate. Existing rows get blank details
# (correct — they simply haven't entered any yet).






