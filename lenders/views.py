from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import LenderInfoForm, LoanApplicationStatusForm, LoanStatusForm
from .models import LenderProfile
from django.contrib import messages
from loans.models import Notification, LoanApplication, Loan, LoanPayment
from django.http import JsonResponse
from borrowers.models import BorrowerProfile, BorrowerDocuments
from loans.models import LoanApplication

from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse

from django.views.generic import ListView, UpdateView
from decimal import Decimal
from datetime import timedelta
from datetime import date
from django.db import models

from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.db.models.functions import TruncMonth

import json
import calendar

from django.utils.timezone import now
from datetime import timedelta

from django.http import JsonResponse
from collections import OrderedDict

from loans.utils import get_loans_by_risk_category

from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required




def lender_index(request):
	if request.user.is_authenticated and request.user.is_lender():
		lender = request.user.lender
		loans = Loan.objects.filter(lender=lender)

		# Total Loans Disbursed
		total_loans_disbursed = loans.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')		
		total_recovered = LoanPayment.objects.filter(loan__in=loans).aggregate(Sum('amount'))['amount__sum'] or 0
		
		# Pull loan applications by this lender
		loan_applications = LoanApplication.objects.filter(lender=lender)

		# New loan applications this week
		one_week_ago = timezone.now() - timedelta(days=7)
		new_loan_applications = loan_applications.filter(date_applied__gte=one_week_ago).count()

		# Count statuses
		pending_loans = loan_applications.filter(status='pending').count()
		approved_loans = loan_applications.filter(status='approved').count()
		rejected_loans = loan_applications.filter(status='rejected').count()

		# Active Loans
		overdue_loans = loans.filter(outstanding_balance__gt=0, due_date__lt=date.today()).count()
		fully_paid_loans = loans.filter(outstanding_balance=0).count()
		
		total_applications = loan_applications.count()

		# Percentages
		pending_percent = int((pending_loans / total_applications) * 100) if total_applications else 0
		approved_percent = int((approved_loans / total_applications) * 100) if total_applications else 0
		rejected_percent = int((rejected_loans / total_applications) * 100) if total_applications else 0
		overdue_percent = int((overdue_loans / total_applications) * 100) if total_applications else 0
		
		
		total_loans = loans.count()
		

		high_risk_count = get_loans_by_risk_category("high").count()
		mid_risk_count = get_loans_by_risk_category("mid").count()
		late_payers_count = get_loans_by_risk_category("late").count()

		# Earnings by month
		#earnings_per_month = (
		#	loans
		#	.filter(repaid_amount__gt=0)
		#	.annotate(month=timezone.datetime.strftime('disbursement_date', "%b"))
		#	.values('month')
		#	.annotate(total=Sum('repaid_amount'))
		#	.order_by('month')
		#)

		earnings_per_month = (
			LoanPayment.objects
			.filter(loan__in=loans)
			.annotate(month=TruncMonth('date_paid'))  
			.values('month')
			.annotate(total=Sum('amount'))
			.order_by('month')
		)

		context = {
			'total_loans_disbursed': total_loans_disbursed,
			'total_loans_recovered': total_recovered,

			# Counts
			'pending_loans': pending_loans,
			'approved_loans': approved_loans,
			'rejected_loans': rejected_loans,
			'overdue_loans': overdue_loans,
			'fully_paid_loans': fully_paid_loans,
			'total_applications': total_applications,

			# Percentages
			'pending_percent': pending_percent,
			'approved_percent': approved_percent,
			'rejected_percent': rejected_percent,
			'overdue_percent': overdue_percent,
			
			
			'new_loan_applications': new_loan_applications,
			'total_loans': total_loans,
			'earnings_data': json.dumps([
				{'month': e['month'].strftime('%b %Y'), 'total': float(e['total'])}
				for e in earnings_per_month
			]),
			'revenue_sources': {
				'Direct': 50,
				'Social': 30,
				'Referral': 20,
			},

			"high_risk_count": high_risk_count,
			"mid_risk_count": mid_risk_count,
			"late_payers_count": late_payers_count,
		}

		return render(request, 'lender_index.html', context)
	else:
		messages.success(request, "You Must Be Logged In To Access That Page!!")
		return redirect('landing')



def lender_profile(request):
	if request.user.is_lender():
		# Get Current User
		current_user = LenderProfile.objects.get(user__id=request.user.id)	
		
		# Get original User Form
		form = LenderInfoForm(request.POST or None, instance=current_user)
						
		if form.is_valid():
			# Save original form
			form.save()
			

			messages.success(request, "Your Info Has Been Updated!!")
			return redirect('lender_index')
		return render(request, "lender_profile.html", {'form':form})
	else:
		messages.success(request, "You Must Be Logged In To Access That Page!!")
		return redirect('landing')


# 1. Monthly Loan Repayments View
def lender_repayment_data(request):
	lender = request.user.lender
	loans = Loan.objects.filter(lender=lender)
	payments = LoanPayment.objects.filter(loan__in=loans)

	# Step 1: Group payments by month
	monthly_totals = payments.annotate(month=TruncMonth('date_paid')).values('month').annotate(
		total=Sum('amount')).order_by('month')

	# Step 2: Build a dictionary for all months with 0 default
	all_months = OrderedDict((calendar.month_name[m], 0) for m in range(1, 13))

	for item in monthly_totals:
		month_name = item['month'].strftime('%B')
		all_months[month_name] = float(item['total'])

	labels = list(all_months.keys())
	data = list(all_months.values())

	# Step 3: Identify high/low months
	if data:
		max_amount = max(data)
		min_amount = min(data)
		high_index = data.index(max_amount)
		low_index = data.index(min_amount)
		high_month = labels[high_index]
		low_month = labels[low_index]
	else:
		high_month = low_month = None
		max_amount = min_amount = 0

	return JsonResponse({
		'labels': labels,
		'data': data,
		'high': {'month': high_month, 'amount': max_amount},
		'low': {'month': low_month, 'amount': min_amount}
	})



# 2. Loan Status Distribution View
def lender_loan_status_data(request):
	lender = request.user.lender

	active = Loan.get_active_loans(lender).count()
	pending = Loan.get_pending_loans(lender).count()
	fully_paid = Loan.get_fully_paid_loans(lender).count()
	overdue = Loan.get_overdue_loans(lender).count()

	return JsonResponse({
		'labels': ['Active', 'Pending', 'Fully Paid', 'Overdue'],
		'data': [active, pending, fully_paid, overdue],
	})



def risk_customer_list(request, category):
	loans = get_loans_by_risk_category(category)
	category_title = {
		"high": "High Risk (Defaulted Loans)",
		"mid": "Mid Risk (Skipped Payments)",
		"late": "Late Payers (Beyond Grace Period)"
	}.get(category, "Unknown Category")

	context = {
		"category": category,
		"category_title": category_title,
		"loans": loans,
	}
	return render(request, "risk_customer_list.html", context)


def mark_loan_application_notifications_read(request):
	Notification.objects.filter(category="loan_application", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})

def mark_loan_payment_notifications_read(request):
	Notification.objects.filter(category="loan_payment", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})



# List all pending loan applications for a specific lender
class LoanApplicationListView(ListView):
	model = LoanApplication
	template_name = 'loan_application_list.html'
	context_object_name = 'loan_applications'

	def get_queryset(self):
		# Filter loan applications by the current lender and status 'pending'
		return LoanApplication.objects.filter(
			lender=self.request.user.lender,
			status='pending'
		).order_by('-date_applied')



# Update the status of a loan application (approve/reject/pending)
class LoanApplicationUpdateView(UpdateView):
	model = LoanApplication
	form_class = LoanApplicationStatusForm
	template_name = 'loan_application_update.html'

	def form_valid(self, form):
		loan_application = form.save(commit=False)
		old_status = LoanApplication.objects.get(pk=loan_application.pk).status
		loan_amount = loan_application.loan_amount
		borrower_user = loan_application.borrower.user

		# Check if status changed
		if loan_application.status != old_status:
			if loan_application.status == 'approved':
				# Only create Loan if not already linked
				if not loan_application.linked_loan:
					loan = Loan.objects.create(
						borrower=loan_application.borrower,
						lender=loan_application.lender,
						amount=Decimal(loan_amount),
						loan_term=loan_application.loan_term,
						interest_rate=Decimal(loan_application.lender.interest_rate),
						first_payment=Decimal(loan_application.first_payment),
						monthly_installment=Decimal(loan_application.monthly_installment),
						total_repayable=loan_amount * (1 + (Decimal(loan_application.lender.interest_rate) / Decimal(100))),
						outstanding_balance=loan_amount * (1 + (Decimal(loan_application.lender.interest_rate) / Decimal(100))),
						due_date=loan_application.date_applied + timedelta(days=365),
						status='approved',
					)
					loan_application.application = loan

				Notification.objects.create(
					user=borrower_user,
					message=f"🎉 Your Loan application from {loan_application.lender.company_name} for R{loan_amount} has been approved.",
					category="loan_approved"
				)

			elif loan_application.status == 'rejected':
				Notification.objects.create(
					user=borrower_user,
					message=f"❌ Your loan of R{loan_amount} from {loan_application.lender.company_name} was rejected. Reason: {loan_application.status_reason}",
					category="loan_rejected"
				)

			elif loan_application.status == 'pending':
				Notification.objects.create(
					user=borrower_user,
					message=f"⏳ Your loan application from {loan_application.lender.company_name} is pending. Reason: {loan_application.status_reason}",
					category="loan_pending"
				)

		loan_application.save()
		return super().form_valid(form)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		loan_application = self.get_object()
		borrower = loan_application.borrower

		# Check outstanding and overdue loans
		outstanding_loans = Loan.objects.filter(borrower=borrower, outstanding_balance__gt=0).count()
		overdue_loans = Loan.objects.filter(borrower=borrower, due_date__lt=date.today(), outstanding_balance__gt=0).count()
		total_debt = Loan.objects.filter(borrower=borrower).aggregate(total=models.Sum('outstanding_balance'))['total'] or 0

		# Add borrower loan history details to context
		context.update({
			'borrower': borrower,
			'loan_amount': loan_application.loan_amount,
			'loan_term': loan_application.loan_term,
			'total_repayable': loan_application.total_repayable,
			'first_payment': loan_application.first_payment,
			'monthly_installment': loan_application.monthly_installment,

			'marital_status': borrower.marital_status,
			'Title': borrower.title,
			'income_amount': borrower.income,
			'date_of_birth': borrower.date_of_birth,
			'phone_number': borrower.phone_number,
			'email_address': borrower.email_address,
			'employer_name': borrower.employer_name,
			'employment_position': borrower.employment_position,
			'position_level': borrower.position_level,
			'home_address': borrower.home_address,
			'employer_address': borrower.employer_address,
			'pay_date': borrower.pay_day,
			'monthly_expenses': borrower.monthly_expenses,
			'existing_debts': borrower.existing_debts,
			'income_type': borrower.income_type,
			'id_number': borrower.id_number,

			'outstanding_loans': outstanding_loans,
			'overdue_loans': overdue_loans,
			'total_debt': total_debt,
		})

		return context

	def get_success_url(self):
		return reverse('loan-application-list')


 
class ApprovedLoansView(ListView):
	model = LoanApplication
	template_name = 'approved_loans.html'
	context_object_name = 'approved_loans'

	def get_queryset(self):
		return LoanApplication.objects.filter(
			lender__user=self.request.user,
			status='approved'
		).select_related('borrower', 'lender')

@login_required
def approved_loans(request):
	lender = get_object_or_404(LenderProfile, user=request.user)
	loans = Loan.objects.filter(lender=lender, status='approved')
	return render(request, 'approved_loans.html', {'loans': loans})


class PendingLoansView(ListView):
	model = LoanApplication
	template_name = 'pending_loans.html'
	context_object_name = 'pending_loans'

	def get_queryset(self):
		return LoanApplication.objects.filter(
			lender__user=self.request.user,
			status='pending'
		).select_related('borrower', 'lender')



@require_POST
@login_required
def update_pending_loans(request):
	submit_id = request.POST.get("submit_id")

	try:
		app = LoanApplication.objects.get(id=submit_id)

		# Reason and status update
		app.status_reason = request.POST.get(f"reason_{app.id}", app.status_reason)
		new_status = request.POST.get(f"status_{app.id}", app.status)

		if new_status == 'approved' and app.status != 'approved':
			loan = Loan.objects.create(
				borrower=app.borrower,
				lender=app.lender,
				amount=Decimal(app.loan_amount),
				loan_term=app.loan_term,
				interest_rate=Decimal(app.lender.interest_rate),
				first_payment=Decimal(app.first_payment),
				monthly_installment=Decimal(app.monthly_installment),
				total_repayable=app.loan_amount * (1 + Decimal(app.lender.interest_rate) / Decimal(100)),
				outstanding_balance=app.loan_amount * (1 + Decimal(app.lender.interest_rate) / Decimal(100)),
				due_date=app.date_applied + timedelta(days=365),
				status='approved'
			)
			app.application = loan
			Notification.objects.create(
				user=app.borrower.user,
				message=f"🎉 Your Loan application from {app.lender.company_name} for R{app.loan_amount} has been approved.",
				category="loan_approved"
			)

		elif new_status == 'rejected':
			Notification.objects.create(
				user=app.borrower.user,
				message=f"❌ Your loan of R{app.loan_amount} was rejected. Reason: {app.status_reason}",
				category="loan_rejected"
			)

		elif new_status == 'pending':
			Notification.objects.create(
				user=app.borrower.user,
				message=f"⏳ Your loan application is pending. Reason: {app.status_reason}",
				category="loan_pending"
			)

		app.status = new_status
		app.save()
		messages.success(request, "Loan application updated.")
	except LoanApplication.DoesNotExist:
		messages.error(request, "Application not found.")

	return redirect('pending-loans')



class RejectedLoansView(ListView):
	model = LoanApplication
	template_name = 'rejected_loans.html'
	context_object_name = 'rejected_loans'

	def get_queryset(self):
		return LoanApplication.objects.filter(lender__user=self.request.user, status='rejected')
 


class OverdueLoansView(ListView):
	model = Loan
	template_name = 'overdue_loans.html'
	context_object_name = 'overdue_loans'

	def get_queryset(self):
		return Loan.objects.filter(
			lender__user=self.request.user,
			due_date__lt=date.today(),
			outstanding_balance__gt=0,
			status='approved'
		)

 

class FullyPaidLoansView(ListView):
	model = Loan
	template_name = 'fully_paid_loans.html'
	context_object_name = 'paid_loans'

	def get_queryset(self):
		return Loan.objects.filter(
			lender__user=self.request.user,
			outstanding_balance=0,
			status='approved'
		)



class LoanStatusUpdateView(UpdateView):
	model = Loan
	form_class = LoanStatusForm
	template_name = 'loan_status_update.html'

	def form_valid(self, form):
		loan = form.save(commit=False)
		# additional logic if needed (e.g., send notification on status change)
		loan.save()
		return super().form_valid(form)

	def get_success_url(self):
		return reverse_lazy('lender-index')


# List all loans (approved or rejected) for a specific lender
class LoanListView(ListView):
	model = Loan
	template_name = 'loan_list.html'
	context_object_name = 'loans'

	def get_queryset(self):
		# Filter loans by the current lender
		return Loan.objects.filter(lender=self.request.user.lender).order_by('-date_created') 

# List all loans  rejected for a specific lender
class RejectedLoanListView(ListView):
	model = LoanApplication
	template_name = 'rejected_loan_list.html'
	context_object_name = 'rejected_loans'

	def get_queryset(self):
		# Filter loans by the current lender
		return LoanApplication.objects.filter(lender=self.request.user.lender, status='rejected')


@login_required
def applied_loans(request):
	try:
		# Ensure the user is a lender
		lender_profile = LenderProfile.objects.get(user=request.user)


		# Fetch loan applications for this lender
		loan_applications = LoanApplication.objects.filter(lender=request.user.lender).order_by('-date_applied') 
		
		# Include borrower profiles and uploaded documents for assessment
		borrowers_data = [
			{
				'loan': loan,
				'borrower_profile': loan.borrower,
				'uploaded_documents': BorrowerDocuments.objects.filter(user=loan.borrower.user),
			}
			for loan in loan_applications
		]

		context = {
			'lender_profile': lender_profile,
			'borrowers_data': borrowers_data,

		}
		return render(request, 'applied_loans.html', context)

	except LenderProfile.DoesNotExist:
		messages.error(request, "You do not have a Lender Profile. Please complete your profile first.")
		return redirect('lender_index')


def borrower_payment_history(request, borrower_id):
	borrower_loans = Loan.objects.filter(borrower_id=borrower_id)
	
	for loan in borrower_loans:
		loan.remaining_months = loan.remaining_months()
		loan.outstanding_balance = loan.outstanding_balance()
		loan.monthly_installment = loan.monthly_installment
		loan.payment_history = loan.payments.all().order_by("-date_paid")

	return render(request, 'borrower_payment_history.html', {'loans': borrower_loans})


@login_required
def my_borrower_payment_history(request, loan_id):
	"""Allows the lender to see a borrower's loan payment history."""
	loan = get_object_or_404(Loan, id=loan_id, lender__user=request.user)
	payments = loan.payments.order_by('-date_paid')  # Get payments (latest first)

	# Calculate months left based on the loan term
	total_months = int(loan.loan_term.split()[0])  # Extract numeric value from term
	months_paid = payments.count()
	months_left = max(total_months - months_paid, 0)

	context = {
		'loan': loan,
		'payments': payments,
		'months_left': months_left,
		'outstanding_balance': loan.outstanding_balance,
	}

	return render(request, 'my_borrower_payment_history.html', context)

# List all loans  paid for a specific lender
class FullyPaidLoanListView(ListView):
	model = Loan
	template_name = 'fully_paid_loan_list.html'
	context_object_name = 'fully_paid_loans'

	def get_queryset(self):
		
		return Loan.objects.filter(lender=self.request.user.lender, status='repaid')


# Clients

@login_required
def my_clients(request):
	lender = request.user.lender

	# Get borrowers who applied for loans from this lender
	clients = (
		Loan.objects.filter(lender=lender)
		.values('borrower__id', 'borrower__user__first_name', 'borrower__user__last_name')
		.annotate(
			total_loans=Count('id'),
			total_amount=Sum('amount'),
			outstanding_balance=Sum('outstanding_balance')
		)
	)

	return render(request, 'my_clients.html', {'clients': clients})

@login_required
def my_clients2(request):
	# Get borrowers who have loans from the logged-in lender
	borrower_ids = Loan.objects.filter(lender=request.user.lender).values_list('borrower', flat=True).distinct()
	borrowers = BorrowerProfile.objects.filter(id__in=borrower_ids)

	return render(request, 'my_clients.html', {'borrowers': borrowers})


def client_documents(request):
	lender = request.user.lender

	# Get borrowers who have taken loans from this lender
	borrower_ids = Loan.objects.filter(lender=lender).values_list('borrower__id', flat=True).distinct()

	# Fetch documents for those borrowers
	documents = BorrowerDocuments.objects.filter(borrower__id__in=borrower_ids).select_related('borrower')

	return render(request, 'client_documents.html', {'documents': documents})

@login_required
def client_documents2(request):
	borrower = BorrowerProfile.objects.get(user=borrower)
	try:
		document = BorrowerDocuments.objects.get(borrower=borrower)
	except BorrowerDocuments.DoesNotExist:
		document = None
	return render(request, 'client_documents.html', {'documents': documents})


@login_required
def credit_reports(request):
	lender = request.user.lender

	# Get borrowers with loans from this lender
	borrower_ids = Loan.objects.filter(lender=lender).values_list('borrower__id', flat=True).distinct()
	borrowers = BorrowerProfile.objects.filter(id__in=borrower_ids).select_related('user')

	borrower_data = []

	for borrower in borrowers:
		loans = Loan.objects.filter(borrower=borrower, lender=lender)
		payments = Payment.objects.filter(loan__in=loans)

		total_loans = loans.count()
		total_borrowed = loans.aggregate(Sum('amount'))['amount__sum'] or 0
		outstanding_balance = loans.aggregate(Sum('outstanding_balance'))['outstanding_balance__sum'] or 0
		total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or 0
		missed_payments = payments.filter(on_time=False).count()  # adjust if you have late logic
		repayment_rate = (total_paid / total_borrowed) * 100 if total_borrowed else 0

		# Optional: assign a simple risk score
		if missed_payments >= 3:
			risk = 'High Risk'
		elif missed_payments > 0:
			risk = 'Medium Risk'
		else:
			risk = 'Low Risk'

		borrower_data.append({
			'borrower': borrower,
			'total_loans': total_loans,
			'total_borrowed': total_borrowed,
			'outstanding_balance': outstanding_balance,
			'total_paid': total_paid,
			'missed_payments': missed_payments,
			'repayment_rate': round(repayment_rate, 2),
			'risk': risk
		})

	return render(request, 'credit_reports.html', {'borrower_data': borrower_data})



