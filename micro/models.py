
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.decorators import user_passes_test




class User(AbstractUser):
	ROLE_CHOICES = (
		('lender', 'Lender'),
		('borrower', 'Borrower'),
	)
	role = models.CharField(max_length=10, choices=ROLE_CHOICES,)
	# Additional fields
	first_name = models.CharField(max_length=15, null=True, blank=True)
	last_name = models.CharField(max_length=15, null=True, blank=True)
	#phone_number = models.CharField(max_length=15, null=True, blank=True)
	#address = models.TextField(null=True, blank=True)

	#def is_lender(user):
	#	return user.is_authenticated and user.role == 'lender'

	#@user_passes_test(is_lender, login_url='landing')
	#def lender_info(request):
	#	return render(request, 'lender_info.html')


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












