from django.db import models
from micro.models import User
from django.db.models.signals import post_save



class LenderProfileManager(models.Manager):
	def get_queryset(self):
		return super().get_queryset().filter(user__role='lender', user__is_superuser=False)



# Create Lender Profile
class LenderProfile(models.Model):

	OWNERSHIP = [
		('', ''),
		('Sole Proprietorship', 'Sole Proprietorship'),
		('Partnership', 'Partnership'),
		('Limited Liability Company', 'Limited Liability Company'),
		('Corporation', 'Corporation'),
	]

	KYC_POLICY_IMPLEMENTATION = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	AML_POLICY_IMPLEMENTATION = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	DATA_PROTECTION_POLICY_IMPLEMENTATION = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	CODE_OF_ETHICS = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	BENCHMARKING = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]

	REPORTING = [
		('', ''),
		('Yes', 'Yes'),
		('No', 'No'),
	]
	RECALCULATION_CHOICES = [
		('recalculate', 'Recalculate Interest on Skipped Payment'),
		('standard', 'Standard Double Payment'),
	]
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='lender')
	ceo_first_name = models.CharField(max_length=20, blank=True)
	ceo_last_name = models.CharField(max_length=20, blank=True)
	date_modified = models.DateTimeField(User, auto_now=True)
	company_name = models.CharField(max_length=20, blank=True)
	registration_no = models.CharField(max_length=20, blank=True)
	office_address = models.CharField(max_length=100, blank=True)
	min_loan = models.DecimalField(decimal_places=2, max_digits=50, blank=True, null=True)
	max_loan = models.DecimalField(decimal_places=2, max_digits=50, blank=True, null=True)
	interest_rate = models.DecimalField(decimal_places=2, max_digits=50, blank=True, null=True)
	phone_number = models.CharField(max_length=20, blank=True)


	date_of_stablishment = models.CharField(max_length=20, blank=True)
	business_email_ddress = models.CharField(max_length=20, blank=True)

	ownership = models.CharField(max_length=100, choices=OWNERSHIP, default='')
	licence_no = models.CharField(max_length=20, blank=True)
	regulatory_body_name = models.CharField(max_length=100, blank=True)
	regulatory_body_no = models.CharField(max_length=100, blank=True)

	kyc_policy_implementation = models.CharField(max_length=100, choices=KYC_POLICY_IMPLEMENTATION, default='')
	aml_policy_implementation = models.CharField(max_length=100, choices=AML_POLICY_IMPLEMENTATION, default='')
	data_protection_policy_implementation = models.CharField(max_length=100, choices=DATA_PROTECTION_POLICY_IMPLEMENTATION, default='')
	tax_number = models.CharField(max_length=50, blank=True)

	code_of_ethics = models.CharField(max_length=100, choices=CODE_OF_ETHICS, default='')
	association_name = models.CharField(max_length=100, blank=True)
	membership_no = models.CharField(max_length=20, blank=True)
	
	benchmarking = models.CharField(max_length=100, choices=BENCHMARKING, default='')
	reporting = models.CharField(max_length=100, choices=REPORTING, default='')

	agrees_to_terms = models.BooleanField(default=False)
	agrees_to_credit_conditions = models.BooleanField(default=False)

	missed_payment_policy = models.CharField(
		max_length=20,
		choices=RECALCULATION_CHOICES,
		default='standard',
		help_text="How this lender handles missed payments."
	)


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

