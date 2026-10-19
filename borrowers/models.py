from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
#from micro.models import User
#from loans.models import LoanApplication
import datetime
from django.db.models.signals import post_save
import os 
from django.utils.text import slugify
import uuid
from django.contrib.auth import get_user_model
from django.conf import settings

from django.utils import timezone

from micro.models import PaymentDetailsMixin


class BorrowerProfileManager(models.Manager):
	def get_queryset(self):
		return super().get_queryset().filter(user__role='borrower', user__is_superuser=False)

def get_upload_path(instance, filename):
	ext = filename.split('.')[-1]
	return f"Borrower-photos/{instance.user.username}.{ext}"

User = get_user_model()


class BorrowerProfile(PaymentDetailsMixin, models.Model):

	GENDER_CHOICES = [
		#('', ''),
		('Male', 'Male'),
		('Female', 'Female'),
		('Other', 'Other'),
	]

	TITLE_CHOICES = [
		#('', ''),
		('Mr', 'Mr.'),
		('Ms', 'Ms.'),
		('Mrs', 'Mrs.'),
		('Dr', 'Dr.'),
		('Prof', 'Prof.'),
	]

	POSITION_LEVEL_CHOICES = [
		#('', ''),
		('entry-level', 'Entry-level'),
		('intermediate', 'Intermediate'),
		('senior-level', 'Senior-level'),
		('business-owner', 'Business owner'),
	]

	INCOME_TYPE_CHOICES = [
		#('', ''),
		('Salary', 'Salary'),
		('Wages', 'Wages'),
		('other', 'Other'),
	]

	MARITAL_STATUS_CHOICES = [
		#('', ''),
		('Single', 'Single'), 
		('Married', 'Married'), 
		('Divorced', 'Divorced'), 
		('Widowed', 'Widowed')
	]

	MONTHLY_EXPENSES_CHOICES = [
		#('', ''),
		('Rent', 'Rent'), 
		('Utilities', 'Utilities'),
		('Debt payment', 'Debt payment'),
		('Insurence', 'Insurence'),
		('Stokvel', 'Stokvel'),
		('other', 'Other'),
	]

	EXISTING_DEBTS_CHOICES = [
		#('', ''),
		('yes', 'Yes'), 
		('no', 'No'),
	]

	EMPLOYMENT_CHOICES = [
		('employed', 'Employed'),
		('self_employed', 'Self-Employed (Unregistered)'),
		('registered_business', 'Self-Employed (Registered)'),
	]

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='borrower', null=True, blank=True)
	full_name = models.CharField(max_length=100, default='')
	gender = models.CharField(max_length=100, choices=GENDER_CHOICES, null=True, blank=True)
	title = models.CharField(max_length=4, choices=TITLE_CHOICES, null=True, blank=True)
	date_of_birth = models.CharField(max_length=20, null=False, default='')
	id_number = models.CharField(max_length=30, null=False, default='')
	marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, null=True, blank=True)
	phone_number = models.CharField(max_length=100, null=True, default='')
	email_address = models.CharField(max_length=100, null=True, default='')
	employer_name = models.CharField(max_length=100, null=True, default='')
	
	income = models.DecimalField(default=0, decimal_places=2, max_digits=50)
	position_level = models.CharField(max_length=50, choices=POSITION_LEVEL_CHOICES, null=True, blank=True)
	
	home_address = models.CharField(max_length=100, null=False, default='')
	employer_address = models.CharField(max_length=100, null=False, default='')
	
	income_type = models.CharField(max_length=100, choices=INCOME_TYPE_CHOICES, null=True, blank=True)
	
	pay_day = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(31)],
		help_text="Day of the month you usually receive your salary (1–31).",
		null=True, blank=True
	)
	passport_photo = models.ImageField(
		upload_to=get_upload_path, 
		null=True, 
		blank=True,
		help_text="Standard KYC passport-sized photo required for identification."
	)
	#monthly_expenses = models.CharField(max_length=100, choices=MONTHLY_EXPENSES_CHOICES, null=True, blank=True)
	existing_debts = models.CharField(max_length=100, choices=EXISTING_DEBTS_CHOICES, null=True, blank=True)
	
	employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, null=True, blank=True)
	
	is_group_admin = models.BooleanField(default=False)
	is_sub_admins = models.BooleanField(default=False)

	is_over_18 = models.BooleanField(default=False)
	agrees_to_terms = models.BooleanField(default=False)
	agrees_to_credit_conditions = models.BooleanField(default=False)
	information_consent = models.BooleanField(default=False)

	objects = BorrowerProfileManager()

	def __str__(self):
		return self.user.username
	


def upload_to(instance, filename):
	return f'documents/{instance.borrower.user.username}/{instance.document_type}/{filename}'




class BorrowerDocs(models.Model):
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	loan_application = models.ForeignKey('loans.LoanApplication', on_delete=models.CASCADE, related_name='loan_documents', null=True, blank=True)
	DOCUMENT_TYPES = [
		('id_proof', 'ID Proof'),
		('bank_statement', 'Bank Statement'),
		('payslip', 'Payslip'),
		('chief_letter', 'Chief Letter'),

		('business_address', 'Business Address'),
		('customer_invoice', 'Customer Invoice'),
		('supplier_invoice', 'Suppliers Invoice'),
		('business_registration', 'Business Registration Certificate'),
		('tax_clearance', 'Tax Clearance Certificate'), # Optional
		('business_statements', 'Business Financial Statements'),
	]
	document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, null=True, blank=True)
	file = models.FileField(upload_to=upload_to)
	upload_date = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.borrower.user.username} - {self.get_document_type_display()}"




class ExpenseAnalysis(models.Model):
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	loan_application = models.ForeignKey('loans.LoanApplication', on_delete=models.CASCADE, related_name='expenses', null=True, blank=True)
	expense_type = models.CharField(max_length=500)
	amount = models.DecimalField(max_digits=10, decimal_places=2)

	def __str__(self):
		return f"{self.borrower.user.username} - {self.expense_type}: {self.amount}"



"""
Layer 6 — DocumentCheckRun model.

Stores a FROZEN snapshot of one verification run: the band, every flag with its
reason, who ran it, and when. Immutable by convention — a new run is a new row,
never an edit of an old one — so a result the lender saw can't be silently
rewritten by a later re-upload or a parser change. Same discipline as KFS.

It NEVER stores "verified/genuine". It stores "assessed on <date>, band=<band>,
these flags". A human reads it and decides.
"""
class DocumentCheckRun(models.Model):
	# --- what was checked ---
	# FK to your borrower document model. Adjust the target + related_name.
	document = models.ForeignKey(
		BorrowerDocs,            
		on_delete=models.CASCADE,
		related_name="check_runs",
	)

	DOC_TYPE_CHOICES = [
		("bank_statement", "Bank statement"),
		("payslip", "Payslip"),
		("national_id", "National ID"),
		("other", "Other"),
	]
	doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES,
								default="bank_statement")

	# --- the frozen result ---
	BAND_CHOICES = [
		("high", "High confidence"),
		("medium", "Medium confidence"),
		("low", "Low confidence"),
		("flagged", "Flagged"),
		("unverifiable", "Could not verify"),
	]
	band = models.CharField(max_length=20, choices=BAND_CHOICES)

	# Every CheckResult, as data: [{code,label,outcome,strength,detail}, ...]
	# This is the snapshot — the exact flags the lender saw, kept verbatim.
	results = models.JSONField(default=list)

	# Convenience counts (denormalised from results, for list views/filtering).
	flag_count = models.PositiveIntegerField(default=0)
	inconclusive_count = models.PositiveIntegerField(default=0)

	# --- audit trail ---
	run_by = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
		null=True, blank=True, related_name="document_check_runs",
		help_text="The lender/staff user who ran these checks.",
	)
	run_at = models.DateTimeField(default=timezone.now)

	# What the engine ran against, for reproducibility/debugging (not shown to
	# borrowers): parse confidence, which check set, whether PDF signals ran.
	meta = models.JSONField(default=dict, blank=True)

	class Meta:
		ordering = ["-run_at"]
		indexes = [
			models.Index(fields=["document", "-run_at"]),
			models.Index(fields=["band"]),
		]

	def __str__(self):
		return f"Check {self.pk} · {self.get_doc_type_display()} · {self.band}"

	# --- read helpers for templates ---

	@property
	def flags(self):
		"""Only the FAIL results — what the lender must look at."""
		return [r for r in self.results if r.get("outcome") == "fail"]

	@property
	def passed(self):
		return [r for r in self.results if r.get("outcome") == "pass"]

	@property
	def inconclusive(self):
		return [r for r in self.results if r.get("outcome") == "inconclusive"]

	@property
	def band_tone(self):
		"""Bootstrap contextual colour for the band badge."""
		return {
			"high": "success",
			"medium": "info",
			"low": "warning",
			"flagged": "danger",
			"unverifiable": "dark",
		}.get(self.band, "secondary")

	@property
	def is_unverifiable(self):
		return self.band == "unverifiable"




