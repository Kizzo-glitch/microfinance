from django.db import models
from lenders.models import LenderProfile
from borrowers.models import BorrowerProfile
#from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
#from micro.models import User
from django.contrib.auth import get_user_model

#from micro.models import User
from datetime import date, timedelta
from django.db.models import Sum
from django.utils.timezone import now
from datetime import date
from django.conf import settings
from multiselectfield import MultiSelectField

from decimal import Decimal

from .references import generate_reference

User = get_user_model()

#User = settings.AUTH_USER_MODEL

# Choices
LOAN_TERM_CHOICES = [

		(1, '1 Month'),
		(2, '2 Months'),
		(3, '3 Months'),
		(4, '4 Months'),
		(5, '5 Months'),
		(6, '6 Months'),
		(7, '7 Months'),
		(8, '8 Months'),
		(9, '9 Months'),
		(10, '10 Months'),
		(11, '11 Months'),
		(12, '12 Months'),
		(24, '24 Months'),
		(36, '36 Months'),
	]

REJECTION_REASONS = [
	('low_credit_score', 'Low credit score'),
	('job_instability', 'Unstable employment or job instability'),
	('high_dti', 'High Debt-to-Income ratio'),
	('insufficient_income', 'Insufficient income'),
	('incomplete_docs', 'Incomplete or incorrect documentation (post 14 days pending)'),
	('income_requirement_not_met', 'Income requirements not met'),
	('high_existing_debts', 'High volume of Existing debts'),
	('insufficient_credit_history', 'Insufficient credit history'),
	('public_records', 'Items of public record'),
	('multiple_loans', 'Multiple loan applications or Excessive loan take outs'),
	('default_existing_loans', 'Default on existing loans'),
]

PENDING_REASONS = [
	('outstanding_docs', 'Outstanding documentation'),
	('inconsistent_info', 'Inconsistent or mismatched information'),
	('recent_activity', 'Recent application activity'),
	('income_instability', 'Income instability or unclear source of funds'),
	('unverified_contact', 'Unverified contact details'),
	('unverifiable_documentation', 'Expenses Self-declared (Unverifiable documents)'),
]




# Loan Application Model
class LoanApplication(models.Model):
	LOAN_STATUS_CHOICES = [
		("draft", "Draft (Incomplete)"),
		('pending', 'Pending'),
		('rejected', 'Reject'),
		('approved', 'Approve'),
		("review", "Submitted For Review"),		
	]
	
	LOAN_STAGE_CHOICES = [
		("employment_type", "Employment Type"),
		("documents", "Upload Documents"),
		("affordability", "Affordability"),
		
		("loan_calculator", "Loan Calculator"),
		("apply_loan", "Apply Loan"),
		("submitted", "Final Review"),
				
	]

	SOURCE_CHOICES = [
		("app", "Mobile App"),
		("ussd", "USSD"),
		("web", "Web"),
	]

	source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="web")
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE, null=True, blank=True)
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, null=True, blank=True)
	loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	total_repayable = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	first_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	loan_term = models.PositiveIntegerField(choices=LOAN_TERM_CHOICES, default=3)

	status = models.CharField(max_length=50, choices=LOAN_STATUS_CHOICES, default='draft')
	status_reason = models.TextField(blank=True, null=True) 
	date_applied = models.DateTimeField(default=timezone.now)

	rejection_reasons = MultiSelectField(choices=REJECTION_REASONS, blank=True)
	pending_reasons = MultiSelectField(choices=PENDING_REASONS, blank=True)
	status_last_updated = models.DateTimeField(auto_now=True)

	linked_loan = models.OneToOneField(
		'Loan',
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name='application_source'
	)

	is_deleted = models.BooleanField(default=False)

	current_stage = models.CharField(
		max_length=50,
		choices=LOAN_STAGE_CHOICES,
		default="employment_type"
	)
	reference_number = models.CharField(
		max_length=20, unique=True, editable=False, null=True, blank=True,
		help_text="Public reference, e.g. FG-2026-A3F9K2. Safe to share; the "
				  "handle borrower and lender cite for any query or dispute.",
	)
	def save(self, *args, **kwargs):
		if not self.reference_number:
			self.reference_number = generate_reference(
				LoanApplication, "reference_number", prefix="FG"
			)
		super().save(*args, **kwargs)


	def is_draft(self):
		return self.status == "draft"

	def __str__(self):
		return f"Application {self.id} - {self.borrower.user.username} - {self.lender.user.username} - {self.status}"


	def get_rejection_reasons_display(self):
		return [dict(self.REJECTION_REASONS).get(reason, reason) for reason in self.rejection_reasons]

	def get_pending_reasons_display(self):
		return [dict(self.PENDING_REASONS).get(reason, reason) for reason in self.pending_reasons]



class Loan(models.Model):
	LOAN_STATUS_CHOICES = [
		('fully_paid', 'Fully Paid'),
		('active', 'Active'),
		('overdue', 'Overdue'),
		('defaulted', 'Defaulted'),
	]
	application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, null=True, blank=True)
	
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE, related_name='loans')
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='loans_given')
	loan_term = models.CharField(max_length=100, choices=LOAN_TERM_CHOICES, default='')
	amount = models.DecimalField(default=0, max_digits=12, decimal_places=2)
	interest_rate = models.DecimalField(default=0, max_digits=5, decimal_places=2)
	first_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	outstanding_balance = models.DecimalField(default=0, max_digits=12, decimal_places=2)
	total_repayable = models.DecimalField(default=0, max_digits=12, decimal_places=2, help_text="Total amount to be repaid")
	status = models.CharField(max_length=10, choices=LOAN_STATUS_CHOICES, default='pending')
	status_reason = models.TextField(blank=True, null=True) 
	due_date = models.DateField()
	
	date_created = models.DateField(auto_now_add=True)
	first_payment_day = models.DateField(null=True, blank=True)
	reference_number = models.CharField(
		max_length=20, unique=True, editable=False, null=True, blank=True,
		help_text="Public loan reference, e.g. FGL-2026-B7Q4M9. Distinct from "
				  "the application reference; linked via the application.",
	)

	def __str__(self):
			return f"Loan {self.id} - {self.borrower.user.username} - {self.lender.user.username} - {self.status}"		

	def save(self, *args, **kwargs):
		# 1. Generate the reference number if it doesn't exist
		if not self.reference_number:
			self.reference_number = generate_reference(
				Loan, "reference_number", prefix="FGL"
			)
		
		# 2. Calculate totals and balances
		self.calculate_total_repayable()
		
		if not self.outstanding_balance:
			self.outstanding_balance = 0
			
		# 3. Call the parent save method EXACTLY ONCE
		super().save(*args, **kwargs)

	def calculate_total_repayable(self):
		"""Calculate the total amount to be repaid including interest."""
		self.total_repayable = self.amount * (1 + (self.interest_rate / 100))

	def remaining_months(self):
		"""Calculate months left until the due date."""
		today = timezone.now().date()
		return max((self.due_date.year - today.year) * 12 + (self.due_date.month - today.month), 0)

	def total_paid(self):
		"""Calculate the total amount paid so far."""
		return self.payments.filter(status="confirmed").aggregate(
			total=Sum('amount'))['total'] or Decimal('0.00')
	
	def total_paid2(self):
		"""Calculate the total amount paid so far."""
		return self.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

	def is_fully_paid(self):
		"""Check if the loan is fully paid."""
		return self.outstanding_balance == Decimal('0.00')


	@classmethod
	def get_active_loans(cls, lender):
		return cls.objects.filter(lender=lender, status='approved', outstanding_balance__gt=0)

	@classmethod
	def get_pending_loans(cls, lender):
		return LoanApplication.objects.filter(lender=lender, status='pending')

	@classmethod
	def get_fully_paid_loans(cls, lender):
		return cls.objects.filter(lender=lender, outstanding_balance=0)

	@classmethod
	def get_overdue_loans(cls, lender):
		return cls.objects.filter(lender=lender, due_date__lt=date.today(), outstanding_balance__gt=0)


	def is_defaulted(self):
		"""Loan is defaulted if the borrower has made no payments and due date passed."""
		return self.outstanding_balance == self.total_repayable and self.due_date < timezone.now().date()

	def is_late(self):
		"""Loan is considered late if the last due date + grace period (7 days) has passed and payment is overdue."""
		grace_date = self.due_date + timezone.timedelta(days=7)
		return self.outstanding_balance > 0 and grace_date < timezone.now().date()

	def missed_payments(self):
		"""Returns True if expected payments are missing (mid-risk behavior)."""
		expected_payments = (timezone.now().date() - self.date_created).days // 30
		#actual_payments = self.payments.count()
		actual_payments = self.payments.filter(status="confirmed").count()
		return actual_payments < expected_payments

	

	def update_outstanding_balance2(self):
		total_paid = sum(payment.amount for payment in self.payments.all())
		self.outstanding_balance = max(self.total_repayable - total_paid, 0)
		self.save()
	
	@property
	def first_payment_date(self):
		"""Return the first payment date (either set manually or 30 days from creation)."""
		if self.first_payment_day:
			return self.first_payment_day
		return self.date_created + timedelta(days=30)

	@property
	def days_until_first_payment(self):
		days_left = (self.first_payment_date - date.today()).days
		return max(days_left, 0)

	@property
	def is_first_payment_overdue(self):
		return self.first_payment_date < date.today()

	def update_outstanding_balance(self):
		"""
		Recompute outstanding balance = total_repayable - sum(confirmed payments).
		Called after a payment is confirmed (or a confirmation is reversed).
		"""
		confirmed = self.payments.filter(status="confirmed").aggregate(
			total=models.Sum("amount")
		)["total"] or Decimal("0.00")
 
		total_repayable = self.total_repayable or Decimal("0.00")
		self.outstanding_balance = max(total_repayable - confirmed, Decimal("0.00"))
 
		# Optional: auto-close a fully-paid loan.
		# if self.outstanding_balance <= 0 and self.status == "approved":
		#     self.status = "settled"
 
		self.save(update_fields=["outstanding_balance"])
 
	@property
	def total_confirmed_paid(self):
		from loans.models import LoanPayment
		return LoanPayment.confirmed_total(self)
 
	@property
	def total_pending_claims(self):
		"""Claimed but not yet confirmed — show as 'pending', not as paid."""
		from loans.models import LoanPayment
		return LoanPayment.claimed_total(self)

	


"""
Fedha-Grow — LoanPayment
===================================
Payments in a "funds never through us" model. Money moves borrower -> lender
externally; the platform RECORDS and RECONCILES it. A payment is therefore a
claim until the party who received the money (the lender) confirms it.

Core rules:
  - A CLAIM does not reduce the outstanding balance and does not count as arrears.
  - Only CONFIRMATION (by the lender) settles a payment and updates the balance.
  - Every payment carries its own reference, and can attach proof.
  - `flow` separates how it was verified (external today / gateway later);
	`method` is the human channel (bank / mpesa / ecocash / cash / gateway).
	The two grow independently — a new channel is a method; a new rail is a flow.

Group payments are not built yet (no group-payer today), but the design leaves
room: a future `paid_by_group` FK is additive and changes nothing here.
"""


class LoanPayment(models.Model):

	STATUS_CHOICES = [
		("claimed",   "Claimed (awaiting lender confirmation)"),
		("confirmed", "Confirmed by lender"),
		("rejected",  "Rejected (not received)"),
		("disputed",  "Disputed"),
	]

	FLOW_CHOICES = [
		("external", "External (paid outside the platform)"),
		("gateway",  "Gateway (confirmed by payment rail)"),
	]

	METHOD_CHOICES = [
		("bank",    "Bank transfer"),
		("mpesa",   "M-Pesa"),
		("ecocash", "EcoCash"),
		("cash",    "Cash"),
		("gateway", "In-app payment"),
	]

	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="payments")

	amount = models.DecimalField(max_digits=12, decimal_places=2)

	flow   = models.CharField(max_length=10, choices=FLOW_CHOICES, default="external")
	method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="bank")
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="claimed")

	# Shared reconciliation key, plus optional external txn ref from the channel.
	reference          = models.CharField(max_length=24, unique=True, editable=False,
										  null=True, blank=True)
	external_reference = models.CharField(max_length=120, blank=True,
										  help_text="The borrower's own transaction reference "
													"from the bank/mobile-money channel, if any.")
	proof = models.FileField(upload_to="payment_proofs/", null=True, blank=True,
							 help_text="Borrower's proof of payment (screenshot, statement, receipt).")

	# lifecycle timestamps
	date_paid    = models.DateTimeField(default=timezone.now,
										help_text="When the borrower says the payment was made.")
	claimed_at   = models.DateTimeField(default=timezone.now)
	confirmed_at = models.DateTimeField(null=True, blank=True)
	confirmed_by = models.ForeignKey(LenderProfile, on_delete=models.SET_NULL,
									 null=True, blank=True, related_name="confirmed_payments")

	note = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(default=timezone.now)

	class Meta:
		ordering = ["-date_paid"]

	def __str__(self):
		return f"{self.reference or 'payment'} — M{self.amount} on Loan {self.loan_id} ({self.status})"

	# ---- lifecycle ----
	def save(self, *args, **kwargs):
		if not self.reference:
			self.reference = generate_reference(LoanPayment, "reference", prefix="FGP")
		# NOTE: saving does NOT touch the loan balance. Only confirm() does.
		# If a payment is created already confirmed (lender-recorded), set
		# confirmed_at first, then call refresh on the loan after save.
		super().save(*args, **kwargs)

	def confirm(self, by_lender=None):
		"""Lender confirms receipt. This is what settles the payment."""
		if self.status == "confirmed":
			return
		self.status = "confirmed"
		self.confirmed_at = timezone.now()
		if by_lender is not None:
			self.confirmed_by = by_lender
		self.save(update_fields=["status", "confirmed_at", "confirmed_by"])
		self._apply_to_balance()

	def reject(self, by_user=None, reason=""):
		"""Lender says the payment was not received."""
		self.status = "rejected"
		if by_user is not None:
			self.confirmed_by = by_user
		if reason:
			self.note = reason[:255]
		self.save(update_fields=["status", "confirmed_by", "note"])
		# A rejection never reduced the balance (only confirm does), so nothing
		# to reverse unless it was previously confirmed — handled below.

	def _apply_to_balance(self):
		"""Recompute the loan balance from CONFIRMED payments only."""
		if hasattr(self.loan, "update_outstanding_balance"):
			self.loan.update_outstanding_balance()

	@property
	def is_settled(self) -> bool:
		return self.status == "confirmed"

	@property
	def awaiting_confirmation(self) -> bool:
		return self.status == "claimed"

	# ---- totals ----
	@staticmethod
	def confirmed_total(loan) -> Decimal:
		"""The real paid figure — drives the balance. Confirmed only."""
		return loan.payments.filter(status="confirmed").aggregate(
			total=models.Sum("amount"))["total"] or Decimal("0.00")

	@staticmethod
	def claimed_total(loan) -> Decimal:
		"""Claimed-but-unconfirmed — for display ('pending'), NOT the balance."""
		return loan.payments.filter(status="claimed").aggregate(
			total=models.Sum("amount"))["total"] or Decimal("0.00")

	# ---- lateness (provisional until a real schedule exists) ----
	def was_late_payment(self, grace_days: int = 7) -> bool:
		"""
		Provisional lateness check based on CONFIRMED payment count and a flat
		30-day cadence. This is a placeholder until the installment schedule is
		built — at which point lateness is measured against scheduled due dates.
		"""
		if self.status != "confirmed":
			return False
		confirmed_before = self.loan.payments.filter(
			status="confirmed", date_paid__lt=self.date_paid
		).count()
		
		anchor = getattr(self.loan, "date_created", None) or self.loan.date_applied
		expected_due = anchor + timedelta(days=30 * (confirmed_before + 1))
		return self.date_paid.date() > (expected_due + timedelta(days=grace_days)).date()



class Notification(models.Model):
	CATEGORY_CHOICES = [
		('loan_application', 'Loan Application'),
		('loan_payment', 'Loan Payment'),
		('payment_update', 'Payment Update'),
		('loan_approved', 'Loan Approved'),
		('loan_rejected', 'Loan Rejected'),
		
		('loan_update', 'Loan Update'),
		('document_update', 'Documents Updated'),
		('loan_deleted', 'Loan Deleted'),
	
	]
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
	loan_application = models.ForeignKey(LoanApplication, null=True, blank=True, on_delete=models.CASCADE)  # ✅ For loan applications
	loan = models.ForeignKey(Loan, null=True, blank=True, on_delete=models.CASCADE)
	#lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='lender_notifications')
	#borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE, related_name='borrower_notifications', null=True)
	message = models.TextField()
	date_created = models.DateTimeField(auto_now_add=True)
	is_read = models.BooleanField(default=False)
	category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='loan_application')

	def __str__(self):
		return f"Notification for {self.user.username} - {self.category} - {self.message[:50]}"



# Risk Notification Model
class RiskNotification(models.Model):
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE)
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	risk_level = models.CharField(max_length=50)
	reason = models.TextField()
	date_notified = models.DateTimeField(default=timezone.now)
	
	def __str__(self):
		return f"Risk Notification - {self.borrower.user.username} - {self.risk_level}"

# Interest Rate Model (can be used to display different rates for each lender)
class InterestRate(models.Model):
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE)
	interest_rate = models.DecimalField(default=0, max_digits=5, decimal_places=2, help_text="Lender-specific interest rate (%)")
	date_effective = models.DateField()

	def __str__(self):
		return f"Interest Rate - {self.lender.business_name} - {self.interest_rate}%"



# Credit History Model
class CreditHistory(models.Model):
	LOAN_STATUS_CHOICES = [
		('pending', 'Pending'),
		('approved', 'Approved'),
		('rejected', 'Rejected'),
		('fully_paid', 'Fully Paid'),
		('active', 'Active'),
		('overdue', 'Overdue'),
		('defaulted', 'Defaulted'),
	]
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
	status = models.CharField(max_length=10, choices=LOAN_STATUS_CHOICES, default='pending')
	date_updated = models.DateTimeField(default=timezone.now)

	def __str__(self):
		return f"Credit History for {self.borrower.user.username} - {self.loan.status}"


User = get_user_model()

class Rating(models.Model):
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='ratings')
	borrower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings')
	rating = models.PositiveIntegerField(
		validators=[
			MinValueValidator(1),
			MaxValueValidator(5)
		]
	)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.borrower.username} rated {self.lender.company_name}: {self.rating}"



# =====================================================================L
#    One assessment per application, created at submission, never edited.
# =====================================================================
class ResponsibleLendingAssessment(models.Model):
	"""
	Immutable snapshot of the affordability assessment captured at the moment
	a loan application is submitted. Audit record — never edited after create.
	"""
 
	OUTCOME_CHOICES = [
		("comfortable",  "Comfortable"),
		("tight",        "Tight"),
		("unaffordable", "Unaffordable"),
	]
 
	borrower = models.ForeignKey(
		"borrowers.BorrowerProfile", on_delete=models.PROTECT,
		related_name="affordability_assessments",
	)
	lender = models.ForeignKey(
		"lenders.LenderProfile", on_delete=models.PROTECT,
		related_name="affordability_assessments",
	)
	loan_application = models.OneToOneField(
		"loans.LoanApplication", on_delete=models.CASCADE,
		related_name="affordability_assessment",
	)
 
	# --- financial snapshot ---
	monthly_income               = models.DecimalField(max_digits=12, decimal_places=2)
	monthly_expenses             = models.DecimalField(max_digits=12, decimal_places=2)
	existing_monthly_commitments = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	monthly_installment          = models.DecimalField(max_digits=12, decimal_places=2)
 
	disposable_income_before     = models.DecimalField(max_digits=12, decimal_places=2)
	disposable_income_after      = models.DecimalField(max_digits=12, decimal_places=2)
 
	# --- ratios (percentages of income) ---
	installment_to_income        = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
	debt_to_income_ratio         = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
	affordability_index_after    = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"),
													   help_text="Percentage of income remaining after the new loan.")
 
	# --- existing exposure ---
	existing_active_loans        = models.PositiveIntegerField(default=0)
 
	# --- outcome & advice ---
	outcome                      = models.CharField(max_length=20, choices=OUTCOME_CHOICES, default='comfortable')
	recommended_max_loan         = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	recommended_term             = models.PositiveIntegerField(null=True, blank=True)
	advice                       = models.JSONField(default=list, blank=True,
													help_text="Plain-language recommendations for the borrower.")
	# --- document verification (from OCR reconciliation; optional) ---
	expenses_verified            = models.BooleanField(default=False,
									   help_text="True only if a statement was read and outflows were parsed.")
	observed_outflows            = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
									   help_text="Total outflows read from an uploaded statement, if any.")
	expense_discrepancy_flag     = models.BooleanField(default=False,
									   help_text="Declared expenses appear well below observed spending.")
	name_match_flag              = models.BooleanField(default=False,
									   help_text="Statement/ID name did not match the profile name.")
	review_signals               = models.JSONField(default=list, blank=True,
									   help_text="Human-readable flags for lender review. Advisory, not a verdict.")
	# --- audit ---
	engine_version = models.CharField(max_length=20, default="2.0")
	assessed_at    = models.DateTimeField(default=timezone.now)
	created_at     = models.DateTimeField(auto_now_add=True)
 
	class Meta:
		ordering = ["-assessed_at"]
		verbose_name = "Affordability Assessment"
		verbose_name_plural = "Affordability Assessments"
 
	def __str__(self):
		return f"{self.loan_application.reference_number} — {self.get_outcome_display()}"
 
	@property
	def is_affordable(self) -> bool:
		return self.disposable_income_after >= 0 and self.outcome != "unaffordable"
 