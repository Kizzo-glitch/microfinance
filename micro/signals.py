from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import User



@receiver(post_save, sender=User)
def send_regulator_welcome_email(sender, instance, created, **kwargs):
    # Only run when a NEW user is created and they are a Regulator
    if created and instance.role == 'regulator':
        subject = "Welcome to the Microfinance Regulatory Platform"
        message = f"""
        Hi {instance.first_name},

        An account has been created for you as a Master Regulator. 
        
        Your temporary password is: {instance.password}
        
        Please log in here to secure your account:
        {settings.SITE_URL}
        
        You will be required to change your password immediately upon login.
        """
        send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [instance.email],
            fail_silently=False,
        )