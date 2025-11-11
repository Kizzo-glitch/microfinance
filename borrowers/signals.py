
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import BorrowerProfile  
from django.contrib.auth import get_user_model


User = get_user_model()

"""
@receiver(post_save, sender=User)
def create_or_update_borrower_profile(sender, instance, created, **kwargs):

    # Only manage profiles for borrowers, ignore lenders
    if instance.role != 'borrower':
        return

    # CASE 1: New user created → create profile IF not exists
    if created:
        BorrowerProfile.objects.get_or_create(
            user=instance,
            defaults={
                'phone_number': instance.phone_number,
                'email_address': instance.email
            }
        )
        return

    # CASE 2: Existing user updated → sync profile (but never recreate)
    BorrowerProfile.objects.update_or_create(
        user=instance,
        defaults={
            'phone_number': instance.phone_number,
            'email_address': instance.email
        }
    )


@receiver(post_save, sender=User)
def create_or_update_borrower_profile(sender, instance, created, **kwargs):
    if instance.role != 'borrower':
        return
    
    # If a profile already exists, DO NOT create a new one
    profile, was_created = BorrowerProfile.objects.get_or_create(
        user=instance,
        defaults={
            'phone_number': instance.phone_number,
            'email_address': instance.email
        }
    )

    # If it already existed, update it
    if not was_created:
        profile.phone_number = instance.phone_number
        profile.email_address = instance.email
        profile.save()


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


"""