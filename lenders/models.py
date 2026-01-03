from django.db import models
#from micro.models import User
from django.db.models.signals import post_save


from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import uuid
from django.db.models import Case, When, IntegerField, Value
from django.db.models.functions import Coalesce

User = get_user_model()
	
class LenderProfileManager(models.Manager):
	"""Enhanced manager for LenderProfile"""
	def get_queryset(self):
		return super().get_queryset().filter(user__role='lender', user__is_superuser=False)
	
	def verified(self):
		return self.filter(verification_status__in=['verified', 'licensed'])
	
	def licensed(self):
		return self.filter(verification_status='licensed')
	
	def pending_review(self):
		return self.filter(verification_status__in=['documents_pending', 'under_review'])
	
	def by_tier(self, tier):
		return self.filter(cbl_tier=tier)
	
	def operational(self):
		"""Lenders that can actively lend"""
		return self.filter(
			verification_status__in=['verified', 'licensed'],
			agrees_to_terms=True
		)
	
	def expiring_licenses(self, days=60):
		"""Licenses expiring within X days"""
		cutoff = timezone.now().date() + timedelta(days=days)
		return self.filter(
			cbl_license_expiry__lte=cutoff,
			cbl_license_expiry__gte=timezone.now().date()
		)
	
	def with_compliance_score(self):
		"""Annotate with compliance score"""

		return self.annotate(
			policy_count=models.Sum(
				Case(
					When(has_kyc_policy=True, then=Value(1)),
					When(has_aml_policy=True, then=Value(1)),
					When(has_data_protection_policy=True, then=Value(1)),
					When(has_code_of_ethics=True, then=Value(1)),
					When(has_complaints_procedure=True, then=Value(1)),
					When(has_risk_management_policy=True, then=Value(1)),
					default=Value(0),
					output_field=IntegerField()
				)
			)
		)


class LenderProfile(models.Model):
	"""
	Core lender profile - combines operational settings with CBL compliance status.
	This is the main profile that links to the User model.
	"""
	
	# ============ CHOICES ============
	
	OWNERSHIP_CHOICES = [
		('', 'Select...'),
		('sole_proprietorship', 'Sole Proprietorship'),
		('partnership', 'Partnership'),
		('llc', 'Limited Liability Company'),
		('corporation', 'Corporation'),
		('cooperative', 'Cooperative'),
		('ngo', 'Non-Governmental Organization'),
	]
	
	CBL_TIER_CHOICES = [
		('', 'Not Determined'),
		('tier1', 'Tier 1 - Deposit-Taking MFI'),
		('tier2', 'Tier 2 - Credit-Only (Large, Assets ≥ M10M)'),
		('tier3', 'Tier 3 - Credit-Only (Small, Assets < M10M)'),
		('individual', 'Individual Lender (Under Platform)'),
		('p2p', 'Peer-to-Peer (Under Platform Umbrella)'),
	]
	
	VERIFICATION_STATUS_CHOICES = [
		('unverified', 'Unverified'),
		('documents_pending', 'Documents Pending'),
		('under_review', 'Under Review'),
		('verified', 'Verified (Platform)'),
		('cbl_pending', 'CBL Application Pending'),
		('licensed', 'CBL Licensed'),
		('suspended', 'Suspended'),
		('rejected', 'Rejected'),
	]
	
	MISSED_PAYMENT_POLICY_CHOICES = [
		('recalculate', 'Recalculate Interest on Skipped Payment'),
		('standard', 'Standard Double Payment'),
		('penalty', 'Apply Late Payment Penalty'),
	]
	
	LOAN_TERM_CHOICES = [
		(1, "1 month"),
		(2, "2 months"),
		(3, "3 months"),
		(4, "4 months"),
		(5, "5 months"),
		(6, "6 months"),
		(9, "9 months"),
		(12, "12 months"),
		(18, "18 months"),
		(24, "24 months"),
		(36, "36 months"),
		(48, "48 months"),
		(60, "60 months"),
	]
	
	# ============ CORE FIELDS ============
	user = models.OneToOneField(
		User, 
		on_delete=models.CASCADE, 
		related_name='lender', null=True, blank=True
	)
	uuid = models.UUIDField(null=True, default=uuid.uuid4, editable=False, unique=True)
	
	# ============ COMPANY INFORMATION ============
	
	company_name = models.CharField(
		null=True,
		max_length=200, 
		help_text="Registered company name"
	)
	trading_name = models.CharField(
		max_length=200, 
		blank=True,
		help_text="Trading name if different from registered name"
	)
	registration_number = models.CharField(
		max_length=50,
		blank=True,
		help_text="Company registration number"
	)
	tax_identification_number = models.CharField(
		max_length=50,
		blank=True,
		help_text="Tax Identification Number (TIN)"
	)
	date_of_establishment = models.DateField(
		null=True,
		blank=True,
		help_text="Date company was established"
	)
	ownership_type = models.CharField(
		max_length=50,
		choices=OWNERSHIP_CHOICES,
		default='',
		blank=True
	)
	
	# ============ CONTACT INFORMATION ============
	
	business_email = models.EmailField(
		null=True,
		max_length=254,
		help_text="Primary business email address"
	)
	phone_number = models.CharField(
		null=True,
		max_length=20,
		help_text="Primary contact number"
	)
	alternate_phone = models.CharField(
		max_length=20,
		blank=True
	)
	website = models.URLField(
		max_length=200,
		blank=True
	)
	
	# Physical Address
	physical_address = models.TextField(
		help_text="Physical office address"
	)
	city = models.CharField(max_length=100, default='Maseru')
	district = models.CharField(max_length=100, blank=True)
	postal_address = models.CharField(max_length=200, blank=True)
	
	# ============ LEADERSHIP ============
	
	ceo_first_name = models.CharField(null=True, max_length=100)
	ceo_last_name = models.CharField(null=True, max_length=100)
	ceo_email = models.EmailField(blank=True)
	ceo_phone = models.CharField(max_length=20, blank=True)
	
	# ============ CBL COMPLIANCE & TIER ============
	
	cbl_tier = models.CharField(
		max_length=20,
		choices=CBL_TIER_CHOICES,
		default='',
		blank=True,
		help_text="CBL regulatory tier classification"
	)
	verification_status = models.CharField(
		max_length=20,
		choices=VERIFICATION_STATUS_CHOICES,
		default='unverified'
	)
	cbl_license_number = models.CharField(
		max_length=100,
		blank=True,
		help_text="CBL-issued license number"
	)
	cbl_license_expiry = models.DateField(
		null=True,
		blank=True
	)
	operating_under_platform = models.BooleanField(
		default=False,
		help_text="Operating under platform's umbrella license"
	)
	
	# ============ CAPITAL INFORMATION ============
	
	stated_capital = models.DecimalField(
		max_digits=15,
		decimal_places=2,
		null=True,
		blank=True,
		help_text="Declared capital in Maloti"
	)
	total_assets = models.DecimalField(
		max_digits=15,
		decimal_places=2,
		null=True,
		blank=True,
		help_text="Total assets value"
	)
	
	# ============ LENDING PARAMETERS ============
	
	min_loan_amount = models.DecimalField(
		max_digits=12,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0.01'))]
	)
	max_loan_amount = models.DecimalField(
		max_digits=12,
		decimal_places=2,
		null=True,
		blank=True
	)
	interest_rate = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		null=True,
		blank=True,
		validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
		help_text="Annual interest rate percentage"
	)
	loan_terms = models.JSONField(
		default=list,
		blank=True,
		help_text="Available loan term options in months"
	)
	missed_payment_policy = models.CharField(
		null=True,
		max_length=20,
		choices=MISSED_PAYMENT_POLICY_CHOICES,
		default='standard'
	)
	
	# ============ COMPLIANCE POLICIES (Boolean flags) ============
	
	has_kyc_policy = models.BooleanField(
		default=False,
		help_text="Has implemented KYC policy"
	)
	has_aml_policy = models.BooleanField(
		default=False,
		help_text="Has implemented AML/CFT policy"
	)
	has_data_protection_policy = models.BooleanField(
		default=False,
		help_text="Has implemented data protection policy"
	)
	has_code_of_ethics = models.BooleanField(
		default=False,
		help_text="Has code of ethics/conduct"
	)
	has_complaints_procedure = models.BooleanField(
		default=False,
		help_text="Has consumer complaints procedure"
	)
	has_risk_management_policy = models.BooleanField(
		default=False,
		help_text="Has risk management framework"
	)
	participates_in_benchmarking = models.BooleanField(
		default=False,
		help_text="Participates in industry benchmarking"
	)
	submits_regulatory_reports = models.BooleanField(
		default=False,
		help_text="Submits required regulatory reports"
	)
	
	# ============ REGULATORY BODY MEMBERSHIP ============
	
	regulatory_body_name = models.CharField(
		max_length=200,
		blank=True,
		help_text="Name of regulatory body/association"
	)
	regulatory_body_membership_number = models.CharField(
		max_length=100,
		blank=True
	)
	association_name = models.CharField(
		max_length=200,
		blank=True,
		help_text="Industry association membership"
	)
	association_membership_number = models.CharField(
		max_length=100,
		blank=True
	)
	
	# ============ AGREEMENTS ============
	
	agrees_to_terms = models.BooleanField(default=False)
	agrees_to_credit_conditions = models.BooleanField(default=False)
	agrees_to_cbl_compliance = models.BooleanField(default=False)
	terms_agreed_at = models.DateTimeField(null=True, blank=True)
	
	# ============ METADATA ============
	
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	verified_at = models.DateTimeField(null=True, blank=True)
	verified_by = models.ForeignKey(
		User,
		null=True,
		blank=True,
		on_delete=models.SET_NULL,
		related_name='verified_lenders'
	)
	notes = models.TextField(blank=True, help_text="Internal notes")
	
	objects = LenderProfileManager()
	
	
	class Meta:
		ordering = ['-created_at']
		verbose_name = 'Lender Profile'
		verbose_name_plural = 'Lender Profiles'
	
	def __str__(self):
		return f"{self.company_name} ({self.user.username})"
	
	# ============ PROPERTIES ============
	
	@property
	def ceo_full_name(self):
		return f"{self.ceo_first_name} {self.ceo_last_name}"
	
	@property
	def is_licensed(self):
		return self.verification_status == 'licensed'
	
	@property
	def is_operational(self):
		return self.verification_status in ['verified', 'licensed']
	
	@property
	def requires_cbl_license(self):
		return self.cbl_tier in ['tier1', 'tier2', 'tier3']
	
	@property
	def minimum_capital_requirement(self):
		"""Return minimum capital requirement based on tier"""
		requirements = {
			'tier1': Decimal('10000000'),  # M10M+ (highest)
			'tier2': Decimal('10000000'),  # M10M in assets
			'tier3': Decimal('500000'),    # Below M10M assets
			'individual': Decimal('50000'),
			'p2p': Decimal('10000'),
		}
		return requirements.get(self.cbl_tier, Decimal('0'))
	
	@property
	def minimum_board_size(self):
		"""Return minimum board members required"""
		requirements = {
			'tier1': 5,
			'tier2': 5,
			'tier3': 3,
			'individual': 0,
			'p2p': 0,
		}
		return requirements.get(self.cbl_tier, 0)
	
	@property
	def license_expiry_warning(self):
		"""Check if license is expiring within 60 days"""
		if not self.cbl_license_expiry:
			return False
		return (self.cbl_license_expiry - timezone.now().date()).days <= 60
	
	# ============ METHODS ============
	
	def get_loan_terms_display(self):
		"""Return human-readable loan terms"""
		terms_map = dict(self.LOAN_TERM_CHOICES)
		return [terms_map.get(int(term), f"{term} months") for term in self.loan_terms]
	
	def average_rating(self):
		"""Calculate average rating from related ratings"""
		ratings = self.ratings.all()
		if not ratings.exists():
			return 0
		return sum(r.rating for r in ratings) / ratings.count()
	
	def get_compliance_score(self):
		"""Calculate compliance score based on policies"""
		policies = [
			self.has_kyc_policy,
			self.has_aml_policy,
			self.has_data_protection_policy,
			self.has_code_of_ethics,
			self.has_complaints_procedure,
			self.has_risk_management_policy,
		]
		completed = sum(1 for p in policies if p)
		return int((completed / len(policies)) * 100)
	
	def determine_cbl_tier(self):
		if self.total_assets and self.total_assets >= Decimal('10000000'):
			return 'tier2'
		elif self.stated_capital and self.stated_capital >= Decimal('500000'):
			return 'tier3'
		elif self.stated_capital and self.stated_capital >= Decimal('50000'):
			return 'individual'
		elif self.stated_capital and self.stated_capital >= Decimal('10000'):
			return 'p2p'
		return ''
	
	def can_accept_deposits(self):
		"""Only Tier 1 can accept deposits"""
		return self.cbl_tier == 'tier1' and self.is_licensed
	
	def clean(self):
		"""Model-level validation"""
		errors = {}
		
		# Validate loan amounts
		if self.min_loan_amount and self.max_loan_amount:
			if self.min_loan_amount > self.max_loan_amount:
				errors['min_loan_amount'] = 'Minimum loan cannot exceed maximum loan'
		
		# Validate capital for tier
		if self.cbl_tier and self.stated_capital:
			min_capital = self.minimum_capital_requirement
			if self.stated_capital < min_capital:
				errors['stated_capital'] = f'Minimum capital for {self.get_cbl_tier_display()} is M {min_capital:,.2f}'
		
		# Validate license expiry
		if self.cbl_license_number and not self.cbl_license_expiry:
			errors['cbl_license_expiry'] = 'License expiry date required when license number is provided'
		
		if errors:
			raise ValidationError(errors)
		
	def has_valid_board(self):
		personnel = self.personnel.all()
		has_ceo = personnel.filter(role='ceo').exists()
		director_count = personnel.filter(role='director').count()
		
		if self.cbl_tier == 'tier1':
			return has_ceo and director_count >= 5  # Example requirement
		return has_ceo and director_count >= 1
	
	def save(self, *args, **kwargs):
		# Auto-determine tier if not set
		if not self.cbl_tier and (self.stated_capital or self.total_assets):
			self.cbl_tier = self.determine_cbl_tier()
		
		# Set terms agreement timestamp
		if self.agrees_to_terms and not self.terms_agreed_at:
			self.terms_agreed_at = timezone.now()
		
		super().save(*args, **kwargs)

# Create a user Profile by default when user signs up
def create_profile(sender, instance, created, **kwargs):
	if created:
		lender_profile = LenderProfile(user=instance)
		lender_profile.save()


# Automate the profile thing
post_save.connect(create_profile, sender=User)


"""
class LenderProfile(models.Model):

	OWNERSHIP = [
		(None, 'Select...'),
		('Sole Proprietorship', 'Sole Proprietorship'),
		('Partnership', 'Partnership'),
		('Limited Liability Company', 'Limited Liability Company'),
		('Corporation', 'Corporation'),
	]

	KYC_POLICY_IMPLEMENTATION = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	AML_POLICY_IMPLEMENTATION = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	DATA_PROTECTION_POLICY_IMPLEMENTATION = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	CODE_OF_ETHICS = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	BENCHMARKING = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	REPORTING = [
		(None, 'Select...'),
		('Yes', 'Yes'),
		('No', 'No'),
	]
	RECALCULATION_CHOICES = [
		('recalculate', 'Recalculate Interest on Skipped Payment'),
		('standard', 'Standard Double Payment'),
	]

	VERIFICATION_CHOICES = [
		('unverified', 'Unverified'),
		('pending', 'Pending Review'),
		('verified', 'Verified'),
		('licensed', 'Licensed'),
	]

	LOAN_TERM_CHOICES = [
		(1, "1 month"),
		(3, "3 months"),
		(6, "6 months"),
		(9, "9 months"),
		(12, "12 months"),
		(24, "24 months"),
		(36, "36 months"),
	]

	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lender')
	ceo_first_name = models.CharField(max_length=20, blank=False)
	ceo_last_name = models.CharField( max_length=20, blank=False)
	date_modified = models.DateTimeField(User, auto_now=True)
	company_name = models.CharField(max_length=20, default='')
	registration_no = models.CharField(max_length=20, default='')
	office_address = models.CharField(max_length=100, default='')
	min_loan = models.DecimalField(decimal_places=2, max_digits=50, null=True, blank=True)
	max_loan = models.DecimalField(decimal_places=2, max_digits=50, null=True, blank=True)
	interest_rate = models.DecimalField(decimal_places=2, max_digits=50, null=True, blank=True)
	phone_number = models.CharField(max_length=20, default='')


	date_of_stablishment = models.CharField(max_length=20, default='')
	business_email_ddress = models.CharField(max_length=20, default='')

	ownership = models.CharField(max_length=100, choices=OWNERSHIP, default='', blank=False)
	licence_no = models.CharField(max_length=20, blank=True, default='')
	regulatory_body_name = models.CharField(max_length=100, blank=True, default='')
	regulatory_body_no = models.CharField(max_length=100, blank=True, default='')

	kyc_policy_implementation = models.CharField(max_length=100, choices=KYC_POLICY_IMPLEMENTATION, default='', blank=False)
	aml_policy_implementation = models.CharField(max_length=100, choices=AML_POLICY_IMPLEMENTATION, default='', blank=False)
	data_protection_policy_implementation = models.CharField(max_length=100, choices=DATA_PROTECTION_POLICY_IMPLEMENTATION, default='', blank=False)
	tax_number = models.CharField(max_length=50, default='', blank=False)

	code_of_ethics = models.CharField(max_length=100, choices=CODE_OF_ETHICS, default='', blank=False)
	association_name = models.CharField(max_length=100, default='')
	membership_no = models.CharField(max_length=20, default='')
	
	benchmarking = models.CharField(max_length=100, choices=BENCHMARKING, default='', blank=False)
	reporting = models.CharField(max_length=100, choices=REPORTING, default='', blank=False)

	agrees_to_terms = models.BooleanField(default=False, blank=False)
	agrees_to_credit_conditions = models.BooleanField(default=False, blank=False)

	missed_payment_policy = models.CharField(
		max_length=20,
		choices=RECALCULATION_CHOICES,
		default='standard',
		help_text="How this lender handles missed payments.",
		blank=False,

	)
	verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='unverified')
	loan_terms = models.JSONField(default=list, blank=True)

	def get_loan_terms_display(self):
		terms_map = dict(self.LOAN_TERM_CHOICES)
		return [terms_map[int(term)] for term in self.loan_terms]

	objects = LenderProfileManager()
	
	
	def average_rating(self):
		ratings = self.ratings.all()
		return sum(rating.rating for rating in ratings) / ratings.count() if ratings else 0


	def __str__(self):
		return self.user.username

# Create a user Profile by default when user signs up
def create_profile(sender, instance, created, **kwargs):
	if created:
		lender_profile = LenderProfile(user=instance)
		lender_profile.save()


# Automate the profile thing
post_save.connect(create_profile, sender=User)

"""

def upload_to_lender_docs(instance, filename):
	return f'lender_documents/{instance.lender.user.username}/{instance.document_type}/{filename}'

class LenderDocs(models.Model):
	lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE)
	DOCUMENT_TYPES = [
		('company_registration', 'Company Registration'),
		('financial_statements', 'Financial Statements'),
		('tax_clearance', 'Tax Clearance'),
		('license_certificate', 'Borrowing License'),
		('proof_of_address', 'Business Address Proof'),
		('other', 'Other Supporting Documents'),
	]
	document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
	file = models.FileField(upload_to=upload_to_lender_docs)
	upload_date = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.lender.company_name} - {self.get_document_type_display()}"



