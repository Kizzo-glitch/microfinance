# utils.py

from twilio.rest import Client
from django.conf import settings
import random


def generate_otp():
	return str(random.randint(100000, 999999))

def send_otp_sms(phone_number, otp):
	client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
	message = client.messages.create(
		body=f"Your verification code is {otp}",
		from_=settings.TWILIO_PHONE_NUMBER,
		to=phone_number
	)
	return message.sid



# Simple utility to generate a random 6-digit OTP:
def generate_otp():
    return str(random.randint(100000, 999999))