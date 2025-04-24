from datetime import timedelta
from django.utils import timezone
from decimal import Decimal
from .models import Loan


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
