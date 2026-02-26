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


"""
class User(AbstractUser):
	ROLE_CHOICES = (
		('lender', 'Lender'),
		('borrower', 'Borrower'),
		('regulator', 'Regulator (CBL)'),
	)
	role = models.CharField(max_length=10, choices=ROLE_CHOICES,)
	# Additional fields
	first_name = models.CharField(max_length=150, null=True, blank=True)
	last_name = models.CharField(max_length=150, null=True, blank=True)
	phone_number = models.CharField(max_length=25, null=True, blank=True)
	email = models.EmailField(max_length=254, unique=True, null=True, blank=True)

	def is_lender(self):
		return self.role == 'lender'

	def is_borrower(self):
		return self.role == 'borrower'

	def is_regulator(self):
		return self.role == 'regulator'
	
	def save(self, *args, **kwargs):
		if not self.pk:  # When creating a new user
			self.role = self.role or 'borrower'
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.username} ({self.role})" 
"""

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












