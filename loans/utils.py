from datetime import timedelta
from django.utils import timezone
from decimal import Decimal
from .models import Loan

import requests
from django.conf import settings

import requests
from requests.auth import HTTPBasicAuth
import logging
import random


# Grace period for late payments
GRACE_PERIOD_DAYS = 7

def get_high_risk_loans():
	"""Loans where borrower never paid anything and due date passed."""
	return Loan.objects.filter(outstanding_balance=F('total_repayable'), due_date__lt=timezone.now().date())

def get_mid_risk_loans():
	"""Loans where borrowers missed expected monthly payments."""
	loans = Loan.objects.all()
	return [loan for loan in loans if loan.missed_payments()]  # slow, but logical fallback

def get_late_loans():
	"""Loans where due date + 7 days grace has passed but payment is still not complete."""
	grace_date = timezone.now().date() - timezone.timedelta(days=7)
	return Loan.objects.filter(outstanding_balance__gt=0, due_date__lt=grace_date)


def get_customer_risk_categories():
	return {
		"high_risk": get_high_risk_loans(),
		"mid_risk": get_mid_risk_loans(),
		"late": get_late_loans(),
	}


def get_loans_by_risk_category(category):
	today = timezone.now().date()
	grace_period = timedelta(days=7)

	if category == "high":
		loans = Loan.objects.filter(outstanding_balance__gt=0, due_date__lt=today)
	elif category == "mid":
		loans = Loan.objects.filter(status="ongoing").filter(
			payments__isnull=True,
			date_created__lt=today - timedelta(days=30)
		).distinct()
	elif category == "late":
		late_loans = []
		for loan in Loan.objects.filter(status="ongoing"):
			for payment in loan.payments.all():
				if payment.date_paid.date() > (loan.due_date + grace_period):
					late_loans.append(loan.id)
					break
		loans = Loan.objects.filter(id__in=late_loans)
	else:
		loans = Loan.objects.none()

	return loans


# SMSPortal
logger = logging.getLogger(__name__)

def send_sms_smsportal(destination_number, message_content):
	"""
	Sends an SMS using the SMSPortal API.

	Args:
		destination_number (str): The recipient's phone number (e.g., "27831234567").
								  Ensure it's in international format without leading '+' or '00'.
		message_content (str): The content of the SMS message.

	Returns:
		dict: A dictionary containing the response from the SMSPortal API
			  or an error message.
	"""
	api_key = settings.CLIENT_ID
	api_secret = settings.SMS_API_SECRET
	sender_id = getattr(settings, 'CLIENT_ID', None) # Get sender ID if set

	if not api_key or not api_secret:
		logger.error("SMSPortal API Key or Secret is not configured in settings.py")
		return {"error": "SMS service not configured."}

	basic_auth = HTTPBasicAuth(api_key, api_secret)

	# Ensure destination number is clean (no leading + or 00)
	if destination_number.startswith('+'):
		destination_number = destination_number[1:]
	if destination_number.startswith('00'):
		destination_number = destination_number[2:]

	sms_request_payload = {
		"messages": [
			{
				"content": message_content,
				"destination": destination_number
			}
		]
	}

	# Add sender ID if configured
	if sender_id:
		sms_request_payload["messages"][0]["source"] = sender_id

	try:
		response = requests.post(
			"https://rest.smsportal.com/bulkmessages",
			auth=basic_auth,
			json=sms_request_payload
		)

		response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

		json_response = response.json()
		if response.status_code == 200:
			logger.info(f"SMS sent successfully to {destination_number}: {json_response}")
			return {"success": True, "data": json_response}
		else:
			logger.error(f"Failed to send SMS to {destination_number}. Status: {response.status_code}, Response: {json_response}")
			return {"success": False, "error": json_response}

	except requests.exceptions.HTTPError as http_err:
		logger.error(f"HTTP error sending SMS to {destination_number}: {http_err} - {response.text}")
		return {"success": False, "error": f"HTTP Error: {http_err}, Response: {response.text}"}
	except requests.exceptions.ConnectionError as conn_err:
		logger.error(f"Connection error sending SMS to {destination_number}: {conn_err}")
		return {"success": False, "error": f"Connection Error: {conn_err}. Check internet connection or SMSPortal API endpoint."}
	except requests.exceptions.Timeout as timeout_err:
		logger.error(f"Timeout error sending SMS to {destination_number}: {timeout_err}")
		return {"success": False, "error": f"Timeout Error: {timeout_err}. SMSPortal API is slow or unavailable."}
	except requests.exceptions.RequestException as req_err:
		logger.error(f"An unexpected request error occurred sending SMS to {destination_number}: {req_err}")
		return {"success": False, "error": f"Request Error: {req_err}"}
	except Exception as e:
		logger.error(f"An unexpected error occurred sending SMS to {destination_number}: {e}")
		return {"success": False, "error": f"Unexpected Error: {e}"}





	