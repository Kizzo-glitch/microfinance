from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.db import models



class User(AbstractUser):
	ROLE_CHOICES = (
		('lender', 'Lender'),
		('borrower', 'Borrower'),
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

	def save(self, *args, **kwargs):
		if not self.pk:  # When creating a new user
			self.role = self.role or 'borrower'
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.username} ({self.role})" 


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












