from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from micro.models import User
#from loans.models import LoanApplication
import datetime
from django.db.models.signals import post_save
import os 
from django.utils.text import slugify


class BorrowerProfileManager(models.Manager):
	def get_queryset(self):
		return super().get_queryset().filter(user__role='borrower', user__is_superuser=False)



class BorrowerProfile(models.Model):

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
		('Loans', 'Loans'), 
		('Credit Cards', 'Credit Cards'),
		('Credit Accounts', 'Credit Accounts'),
		('other', 'Other'),
		('No Debts', 'No Debts')
	]

	EMPLOYMENT_CHOICES = [
		('employed', 'Employed'),
		('self_employed', 'Self-Employed (Unregistered)'),
		('registered_business', 'Registered Business'),
	]

	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='borrower')
	full_name = models.CharField(max_length=100, default='')
	gender = models.CharField(max_length=100, choices=GENDER_CHOICES, null=True, blank=True)
	title = models.CharField(max_length=4, choices=TITLE_CHOICES, null=True, blank=True)
	date_of_birth = models.CharField(max_length=20, null=False, default='')
	id_number = models.CharField(max_length=30, null=False, default='')
	marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, null=True, blank=True)
	phone_number = models.CharField(max_length=100, null=False, default='')
	email_address = models.CharField(max_length=100, null=False, default='')
	employer_name = models.CharField(max_length=100, null=False, default='')
	employment_position = models.CharField(max_length=100, null=False, default='')
	income = models.DecimalField(default=0, decimal_places=2, max_digits=50)
	position_level = models.CharField(max_length=50, choices=POSITION_LEVEL_CHOICES, null=True, blank=True)
	
	home_address = models.CharField(max_length=100, null=False, default='')
	employer_address = models.CharField(max_length=100, null=False, default='')
	
	income_type = models.CharField(max_length=100, choices=INCOME_TYPE_CHOICES, null=True, blank=True)
	#pay_date = models.CharField(max_length=100, null=False, default='')
	pay_day = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(31)],
		help_text="Day of the month you usually receive your salary (1–31).",
		null=True, blank=True
	)
	monthly_expenses = models.CharField(max_length=100, choices=MONTHLY_EXPENSES_CHOICES, null=True, blank=True)
	existing_debts = models.CharField(max_length=100, choices=EXISTING_DEBTS_CHOICES, null=True, blank=True)
	

	#credit_score = models.IntegerField(validators=[MinValueValidator(300), MaxValueValidator(850)], default=300)
	#credit_intend = models.CharField(max_length=100, null=False, default='')
	
	employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, null=True, blank=True)

	is_over_18 = models.BooleanField(default=False)
	agrees_to_terms = models.BooleanField(default=False)
	agrees_to_credit_conditions = models.BooleanField(default=False)
	information_consent = models.BooleanField(default=False)

	objects = BorrowerProfileManager()

	def __str__(self):
		return self.user.username
	
# Create a user Profile by default when user signs up
def create_profile(sender, instance, created, **kwargs):
	if created:
		borrower_profile = BorrowerProfile(user=instance)
		borrower_profile.save()


# Automate the profile thing
post_save.connect(create_profile, sender=User)



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
	expense_type = models.CharField(max_length=100)
	amount = models.DecimalField(max_digits=10, decimal_places=2)

	def __str__(self):
		return f"{self.borrower.user.username} - {self.get_expense_type_display()}: {self.amount}"







