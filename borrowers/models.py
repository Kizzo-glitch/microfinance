from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from micro.models import User
import datetime
from django.db.models.signals import post_save 


class BorrowerProfileManager(models.Manager):
	def get_queryset(self):
		return super().get_queryset().filter(user__role='borrower', user__is_superuser=False)


class BorrowerProfile(models.Model):

	GENDER_CHOICES = [
		('', ''),
		('Male', 'Male'),
		('Female', 'Female'),
		('Other', 'Other'),
	]

	TITLE_CHOICES = [
		('', ''),
		('Mr', 'Mr.'),
		('Ms', 'Ms.'),
		('Mrs', 'Mrs.'),
		('Dr', 'Dr.'),
		('Prof', 'Prof.'),
	]

	POSITION_LEVEL_CHOICES = [
		('', ''),
		('entry-level', 'entry-level'),
		('intermediate', 'intermediate'),
		('senior-level', 'senior-level'),
	]

	INCOME_TYPE_CHOICES = [
		('', ''),
		('Salary', 'Salary'),
		('Wages', 'Wages'),
		('Other', 'Other'),
	]

	MARITAL_STATUS_CHOICES = [
		('', ''),
		('Single', 'Single'), 
		('Married', 'Married'), 
		('Divorced', 'Divorced'), 
		('Widowed', 'Widowed')
	]

	MONTHLY_EXPENSES_CHOICES = [
		('', ''),
		('Rent', 'Rent'), 
		('Utilities', 'Utilities'),
		('Debt payment', 'Debt payment'),
		('Insurence', 'Insurence'),
		('Stokvel', 'Stokvel'),
	]

	EXISTING_DEBTS_CHOICES = [
		('', ''),
		('Loans', 'Loans'), 
		('Credit Cards', 'Credit Cards'),
		('Credit Accounts', 'Credit Accounts'),
		('No Debts', 'No Debts')
	]

	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='borrower')
	full_name = models.CharField(max_length=100, default='')
	gender = models.CharField(max_length=100, choices=GENDER_CHOICES, default='')
	title = models.CharField(max_length=4, choices=TITLE_CHOICES, null=False, default='')
	date_of_birth = models.CharField(max_length=20, null=False, default='')
	id_number = models.CharField(max_length=30, null=False, default='')
	marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, null=False, default='')
	phone_number = models.CharField(max_length=100, null=False, default='')
	email_address = models.CharField(max_length=100, null=False, default='')
	employer_name = models.CharField(max_length=100, null=False, default='')
	employment_position = models.CharField(max_length=100, null=False, default='')
	income = models.DecimalField(default=0, decimal_places=2, max_digits=50)
	position_level = models.CharField(max_length=50, choices=POSITION_LEVEL_CHOICES, null=False, default='')
	
	home_address = models.CharField(max_length=100, null=False, default='')
	employer_address = models.CharField(max_length=100, null=False, default='')
	
	income_type = models.CharField(max_length=100, choices=INCOME_TYPE_CHOICES, null=False, default='')
	#pay_date = models.CharField(max_length=100, null=False, default='')
	pay_day = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(1), MaxValueValidator(31)],
		help_text="Day of the month you usually receive your salary (1–31).",
		null=True, blank=True
	)
	monthly_expenses = models.CharField(max_length=100, choices=MONTHLY_EXPENSES_CHOICES, null=False, default='')
	existing_debts = models.CharField(max_length=100, choices=EXISTING_DEBTS_CHOICES, null=False, default='')
	

	credit_score = models.IntegerField(validators=[MinValueValidator(300), MaxValueValidator(850)], default=300)
	credit_intend = models.CharField(max_length=100, null=False, default='')

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


class BorrowerDocuments(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE)
	id_proof = models.FileField(upload_to='documents/id_proof/')
	bank_statement = models.FileField(upload_to='documents/bank_statements/')
	payslip = models.FileField(upload_to='documents/payslips/')
	chief_letter = models.FileField(upload_to='documents/chief_letter/')
	uploaded_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.user.username}'s Documents"

