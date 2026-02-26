from django.db import models
#from micro.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db.models import Avg, Count, Q, F
import uuid
from django.db.models import Case, When, IntegerField, Value
from django.db.models.functions import Coalesce
from django.db.models import ExpressionWrapper, FloatField
from django.db.models.functions import Cast



User = get_user_model()


COMPLIANCE_POLICY_FIELDS = [
		'has_kyc_policy',
		'has_aml_policy',
		'has_data_protection_policy',
		'has_code_of_ethics',
		'has_complaints_procedure',
		'has_risk_management_policy',
	]

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
	"""
	def expiring_licenses(self, days=60):
		#Licenses expiring within X days
		cutoff = timezone.now().date() + timedelta(days=days)
		return self.filter(
			cbl_license_expiry__lte=cutoff,
			cbl_license_expiry__gte=timezone.now().date()
		)
	"""

	def with_compliance_score(self):
	
		total = len(COMPLIANCE_POLICY_FIELDS)
		score_expr = sum(
			Cast(models.F(field), output_field=IntegerField())
			for field in COMPLIANCE_POLICY_FIELDS
		)
		return self.annotate(
			compliance_score=ExpressionWrapper(
				score_expr * Value(100) / Value(total),
				output_field=FloatField()
			)
		)
	
	"""
	def with_compliance_score(self):
		# Annotate with compliance score

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
		"""


def get_upload_path(instance, filename):
	ext = filename.split('.')[-1]
	return f"Lender-photos/{instance.user.username}.{ext}"


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
	]

	PLATFORM_TIER_CHOICES = [
		('', 'Not Applicable'),
		('individual', 'Individual Lender (Platform)'),
		('p2p', 'Peer-to-Peer (Platform Umbrella)'),
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
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lender', null=True, blank=True)
	uuid = models.UUIDField(null=True, default=uuid.uuid4, editable=False, unique=True)
	
	# ============ COMPANY INFORMATION ============
	company_name = models.CharField(null=True, max_length=200, help_text="Registered company name")
	trading_name = models.CharField(max_length=200, blank=True, help_text="Trading name if different from registered name")
	registration_number = models.CharField(max_length=50, blank=True, help_text="Company registration number")
	tax_identification_number = models.CharField(max_length=50, blank=True,help_text="Tax Identification Number (TIN)")
	date_of_establishment = models.DateField(null=True, blank=True, help_text="Date company was established")
	ownership_type = models.CharField(max_length=50, choices=OWNERSHIP_CHOICES, default='', blank=True)
	
	# ============ CONTACT INFORMATION ============
	business_email = models.EmailField(null=True, max_length=254, help_text="Primary business email address")
	phone_number = models.CharField(null=True, max_length=20, help_text="Primary contact number")
	alternate_phone = models.CharField(max_length=20, blank=True)
	website = models.URLField(max_length=200, blank=True)
	
	# Physical Address
	physical_address = models.TextField(help_text="Physical office address")
	city = models.CharField(max_length=100, default='Maseru')
	district = models.CharField(max_length=100, blank=True)
	postal_address = models.CharField(max_length=200, blank=True)
	
	# ============ LEADERSHIP ============
	
	ceo_first_name = models.CharField(null=True, max_length=100)
	ceo_last_name = models.CharField(null=True, max_length=100)
	ceo_email = models.EmailField(blank=True)
	ceo_phone = models.CharField(max_length=20, blank=True)
	passport_photo = models.ImageField(upload_to=get_upload_path, 
		null=True, 
		blank=True,
		help_text="Upload a clear, passport-sized photograph."
	)
	

	# ============ CBL COMPLIANCE & TIER ============
	cbl_tier = models.CharField(max_length=20, choices=CBL_TIER_CHOICES, default='', blank=True,
		help_text="CBL regulatory tier classification"
	)
	platform_tier = models.CharField(max_length=20, choices=PLATFORM_TIER_CHOICES, default='', blank=True,
		help_text="Platform classification for non-CBL-regulated lenders"
	)
	verification_status = models.CharField(max_length=20,choices=VERIFICATION_STATUS_CHOICES,
		default='unverified'
	)
	cbl_license_number = models.CharField(max_length=100,blank=True,
		help_text="CBL-issued license number"
	)
	cbl_license_expiry = models.DateField(null=True, blank=True
	)
	operating_under_platform = models.BooleanField(default=False,
		help_text="Operating under platform's umbrella license"
	)
	
	
	# ============ CAPITAL INFORMATION ============
	
	stated_capital = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
		help_text="Declared capital in Maloti",
		default=0
	)
	total_assets = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True,
		help_text="Total assets value",
		default=0
	)
	
	# ============ LENDING PARAMETERS ============
	
	min_loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,)
	max_loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	interest_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
		validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
		help_text="Annual interest rate percentage")
	loan_terms = models.JSONField(default=list, blank=True,
		help_text="Available loan term options in months")
	missed_payment_policy = models.CharField(null=True, max_length=20, choices=MISSED_PAYMENT_POLICY_CHOICES, default='standard')
	
	# ============ COMPLIANCE POLICIES (Boolean flags) ============
	has_kyc_policy = models.BooleanField(default=False, help_text="Has implemented KYC policy")
	has_aml_policy = models.BooleanField(default=False, help_text="Has implemented AML/CFT policy")
	has_data_protection_policy = models.BooleanField( default=False, help_text="Has implemented data protection policy")
	has_code_of_ethics = models.BooleanField(default=False, help_text="Has code of ethics/conduct")
	has_complaints_procedure = models.BooleanField(default=False, help_text="Has consumer complaints procedure")
	has_risk_management_policy = models.BooleanField(default=False, help_text="Has risk management framework")
	participates_in_benchmarking = models.BooleanField(default=False, help_text="Participates in industry benchmarking")
	submits_regulatory_reports = models.BooleanField(default=False,help_text="Submits required regulatory reports")
	
	# ============ REGULATORY BODY MEMBERSHIP ============
	regulatory_body_name = models.CharField(max_length=200, blank=True, help_text="Name of regulatory body/association")
	regulatory_body_membership_number = models.CharField(max_length=100, blank=True)
	association_name = models.CharField(max_length=200, blank=True,help_text="Industry association membership")
	association_membership_number = models.CharField(max_length=100, blank=True)
	
	# ============ AGREEMENTS ============
	agrees_to_terms = models.BooleanField(default=False)
	agrees_to_credit_conditions = models.BooleanField(default=False)
	agrees_to_cbl_compliance = models.BooleanField(default=False)
	terms_agreed_at = models.DateTimeField(null=True, blank=True)
	
	# ============ METADATA ============
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_approved = models.BooleanField(default=False)
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
		"""Only the three formal CBL tiers require a CBL license."""
		return self.cbl_tier in ('tier1', 'tier2', 'tier3')

	@property
	def is_platform_only(self):
		"""True for individual/P2P lenders operating under platform umbrella."""
		return bool(self.platform_tier) and not self.cbl_tier

	@property
	def minimum_capital_requirement(self):
		requirements = {
			'tier1': Decimal('10000000'),
			'tier2': Decimal('10000000'),
			'tier3': Decimal('500000'),
		}
		return requirements.get(self.cbl_tier, Decimal('0'))

	@property
	def minimum_board_size(self):
		requirements = {
			'tier1': 5,
			'tier2': 5,
			'tier3': 0,  # No minimum per CBL regulations
		}
		return requirements.get(self.cbl_tier, 0)
	

	"""
	@property
	def requires_cbl_license(self):
		# Now includes individuals and P2P under the regulated umbrella
		regulated_tiers = ['tier1', 'tier2', 'tier3', 'individual', 'p2p']
		return self.cbl_tier in regulated_tiers
	
	@property
	def minimum_capital_requirement(self):
		# Return minimum capital requirement based on tier
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
		# Return minimum board members required
		requirements = {
			'tier1': 5,
			'tier2': 5,
			'tier3': 3,
			'individual': 0,
			'p2p': 0,
		}
		return requirements.get(self.cbl_tier, 0)
	"""
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
		"""Returns average rating as a float, or 0 if no ratings exist."""
		result = self.ratings.aggregate(avg=Avg('rating'))['avg']
		return round(result, 1) if result is not None else 0
	
	"""
	def average_rating(self):
		Calculate average rating from related ratings
		#ratings = self.ratings.all()
		#if not ratings.exists():
		#	return 0
		#return sum(r.rating for r in ratings) / ratings.count()
		return self.ratings.aggregate(Avg('rating'))['rating__avg'] or 0
	"""
	
	# On the model:
	def get_compliance_score(self):
		completed = sum(1 for field in COMPLIANCE_POLICY_FIELDS if getattr(self, field))
		return int((completed / len(COMPLIANCE_POLICY_FIELDS)) * 100)
	
	"""
	def get_compliance_score(self):
		# Calculate compliance score based on policies
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
	

	def with_compliance_score(self):
		
		Annotates each LenderProfile with a compliance_score (0–100).
		Mirrors the logic in get_compliance_score() so results are consistent.
		
		policy_fields = [
			'has_kyc_policy',
			'has_aml_policy',
			'has_data_protection_policy',
			'has_code_of_ethics',
			'has_complaints_procedure',
			'has_risk_management_policy',
		]
		total = len(policy_fields)

		# Sum the boolean fields (True=1, False=0) then express as percentage
		score_expr = sum(
			Cast(models.F(field), output_field=IntegerField())
			for field in policy_fields
		)

		return self.annotate(
			compliance_score=ExpressionWrapper(
				score_expr * Value(100) / Value(total),
				output_field=FloatField()
			)
		)
		"""
	
	def determine_cbl_tier(self):
		"""
		Suggests a CBL tier based on assets and deposit-taking intent.

		Per CBL rules:
		- Tier 1: Deposit-taking MFIs — must be explicitly declared, cannot
					be inferred from capital alone. Never auto-assigned here.
		- Tier 2: Credit-only, total assets >= M10,000,000
		- Tier 3: Credit-only, total assets < M10,000,000

		This method only auto-suggests Tier 2 or 3.
		Tier 1 must be set manually via the onboarding form.
		Returns '' if insufficient data to make a suggestion.
		"""
		# If already set to Tier 1 by the user, preserve it.
		if self.cbl_tier == 'tier1':
			return 'tier1'

		# Tiers 2 and 3 are asset-based for credit-only entities.
		if self.total_assets is not None:
			if self.total_assets >= Decimal('10000000'):
				return 'tier2'
			return 'tier3'

		return ''
	

	"""
	def determine_cbl_tier(self):
		if self.total_assets and self.total_assets >= Decimal('10000000'):
			return 'tier2'
		elif self.stated_capital and self.stated_capital >= Decimal('2000000'):
			return 'tier1'		
		elif self.stated_capital and self.stated_capital >= Decimal('500000'):
			return 'tier3'
		elif self.stated_capital and self.stated_capital >= Decimal('50000'):
			return 'individual'
		elif self.stated_capital and self.stated_capital >= Decimal('10000'):
			return 'p2p'
		return ''

	"""
	

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
		"""
		Validates board composition against CBL tier requirements.

		Tier 1 & 2: Minimum 5 directors, chairman must be non-executive,
					all counted directors must be fully verified.
		Tier 3:     No formal board minimum — just needs a CEO/MD.
		"""
		personnel = self.personnel.all()

		has_ceo = personnel.filter(role='ceo').exists()

		if self.cbl_tier == 'tier3':
			return has_ceo

		if self.cbl_tier in ('tier1', 'tier2'):
			directors = personnel.filter(role='director')

			# Only count directors who have passed the full verification check
			verified_directors = [d for d in directors if d.is_fully_verified()]
			verified_count = len(verified_directors)

			if verified_count < 5:
				return False

			# Chairman must be explicitly flagged as non-executive.
			# This requires an `is_non_executive` boolean on PersonnelProfile (see note below).
			has_non_exec_chair = personnel.filter(
				role='director',
				is_chairman=True,
				is_non_executive=True,
			).exists()

			return has_ceo and has_non_exec_chair

		return False
	
	
	def save(self, *args, **kwargs):
		# Auto-determine tier if not set
		if self.cbl_tier not in ('tier1', 'tier2', 'tier3') and self.total_assets is not None:
			self.cbl_tier = self.determine_cbl_tier()
	
		#if not self.cbl_tier and (self.stated_capital or self.total_assets):
		#	self.cbl_tier = self.determine_cbl_tier()
		
		# Set terms agreement timestamp
		if self.agrees_to_terms and not self.terms_agreed_at:
			self.terms_agreed_at = timezone.now()
		
		super().save(*args, **kwargs)


@receiver(post_save, sender=User)
def create_lender_profile(sender, instance, created, **kwargs):
	"""
	Only create a LenderProfile when a lender user is first registered.
	Borrowers, admins, and staff must not get one.
	"""
	if not created:
		return

	if getattr(instance, 'role', None) == 'lender':
		LenderProfile.objects.get_or_create(user=instance)









"""
# Create a user Profile by default when user signs up
def create_profile(sender, instance, created, **kwargs):
	if created:
		lender_profile = LenderProfile(user=instance)
		lender_profile.save()


# Automate the profile thing
post_save.connect(create_profile, sender=User)



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



