
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import BorrowerProfile  
from django.contrib.auth import get_user_model


User = get_user_model()

@receiver(post_save, sender=User)
def create_or_update_borrower_profile(sender, instance, created, **kwargs):
    if instance.role == 'borrower':
        # Check if a BorrowerProfile already exists for this user
        if created:
            BorrowerProfile.objects.create(
                user=instance,
                phone_number=instance.phone_number,
                email_address=instance.email
            )
        else:
            # Update the profile if the user's phone or email changes
            BorrowerProfile.objects.filter(user=instance).update(
                phone_number=instance.phone_number,
                email_address=instance.email
            )