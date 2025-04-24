from django.db import models
from lenders.models import LenderProfile
from borrowers.models import BorrowerProfile
#from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
#from micro.models import User
from django.contrib.auth import get_user_model
from decimal import Decimal
from micro.models import User
from datetime import date, timedelta
from django.db.models import Sum
from django.utils.timezone import now
from datetime import date



# Choices
LOAN_STATUS_CHOICES = [
	('pending', 'Pending'),
	('approved', 'Approved'),
	('rejected', 'Rejected'),
	('fully_paid', 'Fully Paid'),
	('active', 'Active'),
	('overdue', 'Overdue'),
	('defaulted', 'Defaulted'),
]

LOAN_TERM_CHOICES = [
		#('', ''),
		#('6 Months', '6 Months'),
		#('12 Months', '12 Months'),
		#('24 Months', '24 Months'),
		#('36 Months', '36 Months'),

		(3, '3 Months'),
		(6, '6 Months'),
		(12, '12 Months'),
		(24, '24 Months'),
		(36, '36 Months'),
	]

# Loan Application Model
class LoanApplication(models.Model):
	
	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE)
	loan_amount = models.DecimalField(max_digits=12, decimal_places=2)
	
	#collateral = models.CharField(max_length=500, null=False, default='')
	#payment_plan = models.CharField(max_length=500, null=False, default='')

	total_repayable = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	first_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	monthly_installment = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

	loan_term = models.PositiveIntegerField(choices=LOAN_TERM_CHOICES, default=3)

	status = models.CharField(max_length=50, choices=LOAN_STATUS_CHOICES, default='pending')
	status_reason = models.TextField(blank=True, null=True) 
	date_applied = models.DateTimeField(default=timezone.now)

	linked_loan = models.OneToOneField(
		'Loan',
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name='application_source'
	)


	def __str__(self):
		return f"Application {self.id} - {self.borrower.user.username} - {self.lender.user.username} - {self.status}"



class Loan(models.Model):
	application = models.OneToOneField(LoanApplication, on_delete=models.CASCADE, null=True, blank=True)
	# application_source = Reverse OneToOne from LoanApplication (related_name='application_source')
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
	#date_created = models.DateTimeField(default=timezone.now)
	date_created = models.DateField(auto_now_add=True)
	first_payment_day = models.DateField(null=True, blank=True)

	def __str__(self):
		return f"Loan {self.id} - {self.borrower.user.username} - {self.lender.user.username} - {self.status}"

	def save(self, *args, **kwargs):
		"""Ensure total_repayable and outstanding_balance are properly set before saving"""
		self.calculate_total_repayable()  # Ensures correct total repayable
		if not self.outstanding_balance:
			self.outstanding_balance = 0
		super().save(*args, **kwargs)
		

	def calculate_total_repayable(self):
		"""Calculate the total amount to be repaid including interest."""
		self.total_repayable = self.amount * (1 + (self.interest_rate / 100))

	def update_outstanding_balance2(self):
		"""Update outstanding balance based on total payments made."""
		total_paid = self.total_paid()
		#total_paid = self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
		self.outstanding_balance = max(self.total_repayable - total_paid, Decimal('0.00'))
		self.save()

	def remaining_months(self):
		"""Calculate months left until the due date."""
		today = timezone.now().date()
		return max((self.due_date.year - today.year) * 12 + (self.due_date.month - today.month), 0)

	

	
	def total_paid(self):
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


	
	'''@classmethod
	def get_active_loans(cls, lender):
		return cls.objects.filter(lender=lender, status='active')

	@classmethod
	def get_pending_loans(cls, lender):
		return cls.objects.filter(lender=lender, status='pending')

	@classmethod
	def get_fully_paid_loans(cls, lender):
		return cls.objects.filter(lender=lender, outstanding_balance=Decimal('0.00'))

	@classmethod
	def get_overdue_loans(cls, lender):
		return cls.objects.filter(
			lender=lender,
			due_date__lt=now().date(),
			outstanding_balance__gt=Decimal('0.00')
		)'''

	
	'''def is_defaulted(self):
		"""Define a loan as defaulted if it's overdue by more than 30 days and still has outstanding balance."""
		overdue_by = timezone.now().date() - self.due_date
		return self.outstanding_balance > 0 and overdue_by.days > 30'''

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
		actual_payments = self.payments.count()
		return actual_payments < expected_payments

	def update_outstanding_balance3(self):
		total_paid = self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
		self.outstanding_balance = self.total_repayable - total_paid

		# Auto-mark as fully paid if balance is zero
		if self.outstanding_balance <= Decimal('0'):
			self.status = 'fully_paid'
			self.outstanding_balance = Decimal('0')  # Prevent negative balances

		self.save()

	def update_outstanding_balance4(self):
		total_paid = self.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
		self.outstanding_balance = self.total_repayable - total_paid

		if self.outstanding_balance <= Decimal('0'):
			self.outstanding_balance = Decimal('0')
			self.status = 'fully_paid'

		elif date.today() > self.due_date:
			self.status = 'overdue'

		else:
			self.status = 'active'  # Optional: fallback to active if neither fully paid nor overdue

		self.save()

	def update_outstanding_balance(self):
		total_paid = sum(payment.amount for payment in self.payments.all())
		self.outstanding_balance = max(self.total_repayable - total_paid, 0)
		self.save()



	
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




class LoanPayment(models.Model):
	PAYMENT_CHOICES = [
		('bank_account', 'Bank Account'),
		('mpesa', 'Mpesa'),
		('cash', 'Cash'),
	]

	borrower = models.ForeignKey(BorrowerProfile, on_delete=models.CASCADE)
	loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	date_paid = models.DateTimeField(default=timezone.now)
	payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='')

	def __str__(self):
		return f"Payment of R{self.amount} for Loan {self.loan.id} on {self.date_paid.date()}"

	@staticmethod
	def get_total_paid(loan):
		"""Get total amount paid towards a loan."""
		return loan.payments.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

	def save(self, *args, **kwargs):
		"""Update loan outstanding balance on payment."""
		super().save(*args, **kwargs)
		self.loan.update_outstanding_balance()


	def was_late_payment(self):
		"""Returns True if payment was made more than 7 days after due date."""
		expected_due = self.loan.date_created + timedelta(days=30 * self.loan.payments.count())
		grace_period = expected_due + timedelta(days=7)
		return self.date_paid.date() > grace_period



class Notification(models.Model):
	CATEGORY_CHOICES = [
		('loan_application', 'Loan Application'),
		('loan_payment', 'Loan Payment'),
		('loan_approved', 'Loan Approved'),
		('loan_rejected', 'Loan Rejected'),
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





