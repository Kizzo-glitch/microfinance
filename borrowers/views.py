from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from lenders.models import LenderProfile
from loans.models import LoanApplication, Loan, LoanPayment, Notification, Rating
from .forms import LoanApplicationForm, BorrowerDocumentsForm, LoanPaymentForm

import random

from django.contrib import messages

from .forms import RatingForm, BorrowerProfileForm
from .models import BorrowerProfile, BorrowerDocuments
from django.contrib.auth.decorators import login_required
from django.db.models import Avg

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from decimal import Decimal

from django.utils.timezone import now
from datetime import date
from django.db import models

from datetime import timedelta
from django.db.models import Count, Sum, Q
from collections import defaultdict

from django.views.generic import ListView

from dateutil.relativedelta import relativedelta
from datetime import date
from django.utils import timezone


@login_required
def borrower_index(request):
	lenders = (LenderProfile.objects.filter(user__is_superuser=False, user__role='lender')
		.annotate(average_rating=Avg('ratings__rating')))

	for lender in lenders:
		lender.bg_color = generate_random_color()

	return render(request, 'borrower_index.html', {'lenders': lenders})

@login_required
def borrower_profile2(request):
	if request.user.is_borrower():
		# Get Current User
		current_user = BorrowerProfile.objects.get(user__id=request.user.id)	
		
		# Get original User Form
		form = BorrowerProfileForm(request.POST or None, instance=current_user)
						
		if form.is_valid():
			# Save original form
			form.save()
			
			messages.success(request, "Your Info Has Been Updated!!")
			return redirect('borrower_index')
		else:
			print(form.errors)
		return render(request, "borrower_profile.html", {'form':form})
	else:
		messages.success(request, "You Must Be Logged In To Access That Page!!")
		return redirect('landing')

@login_required
def borrower_profile(request):
	if request.user.is_borrower():
		current_user = BorrowerProfile.objects.get(user__id=request.user.id)

		# Get original User Form
		form = BorrowerProfileForm(request.POST or None, instance=current_user)

		# Get borrower's outstanding and overdue loans
		outstanding_loans = Loan.objects.filter(borrower=current_user, outstanding_balance__gt=0).count()
		overdue_loans = Loan.objects.filter(borrower=current_user, due_date__lt=date.today(), outstanding_balance__gt=0).count()
		total_debt = Loan.objects.filter(borrower=current_user).aggregate(total=models.Sum('outstanding_balance'))['total'] or 0

		if form.is_valid():
			form.save()
			messages.success(request, "Your Info Has Been Updated!!")
			return redirect('borrower_index')
		else:
			print(form.errors)

		return render(request, "borrower_profile.html", {
			'form': form,
			'outstanding_loans': outstanding_loans,
			'overdue_loans': overdue_loans,
			'total_debt': total_debt,
		})

	messages.error(request, "You Must Be Logged In To Access That Page!!")
	return redirect('landing')




def upload_documents(request):
	if request.method == 'POST':
		form = BorrowerDocumentsForm(request.POST, request.FILES)
		if form.is_valid():
			user = request.user
			borrower_documents = BorrowerDocuments(user=user) 
			form.save(commit=False)  # Save the form data without committing to the database
			borrower_documents.id_proof = form.cleaned_data['id_proof']
			borrower_documents.bank_statement = form.cleaned_data['bank_statement']
			borrower_documents.payslip = form.cleaned_data['payslip']
			borrower_documents.chief_letter = form.cleaned_data['chief_letter']
			borrower_documents.save() # This will save the uploaded files and form data
			# Handle successful upload (e.g., redirect or success message)
			return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/loan_application/'})
		else:
			# Handle form validation errors
			return JsonResponse({'error': form.errors})
	else:
		form = BorrowerDocumentsForm()  # Create a new form instance for GET requests
	return render(request, 'upload_documents.html', {'form': form})





@login_required
def loan_application(request):
	try:
		# Retrieve borrower profile
		borrower = BorrowerProfile.objects.get(user=request.user)

		 # Retrieve lender details from session
		lender_id = request.session.get('lender_id')
		interest_rate = request.session.get('interest_rate')

		if not lender_id: #or not interest_rate:
			messages.error(request, "No lender selected. Please start again.")
			return redirect('borrower_index')

		lender = LenderProfile.objects.get(id=lender_id)

		#lender = LenderProfile.objects.get(id=lender_id)

		if request.method == 'POST':
			form = LoanApplicationForm(request.POST)
			if form.is_valid():
				# Save loan application
				loan_application = form.save(commit=False)
				loan_application.borrower = borrower
				loan_application.lender = lender

				loan_application.calculate_total_repayable()
				loan_application.calculate_monthly_installment() 
				loan_application.interest_rate = interest_rate
				loan_application.save()

				# Notify lender
				#lender.notifications.create(
				#	message=f"New loan application from {borrower.full_name}"
				#)

				# Notify the lender
				Notification.objects.create(
					user=lender,
					message=f"New loan application from {borrower.full_name}"
				)

				messages.success(request, "Application submitted successfully. Please wait for the Lender to review")
				return redirect('loan-application-success')
		else:
			# Pre-fill lender and interest rate in the form
			form = LoanApplicationForm(initial={
				'lender': lender.id,
				'interest_rate': interest_rate,
			})

		return render(request, 'loan_application.html', {'form': form, 'lender': lender, 'lender_interest_rate': interest_rate})
	
	except BorrowerProfile.DoesNotExist:
		messages.error(request, "You do not have a Profile. Please complete your profile first.")
		return redirect('borrower_profile')




def loan_calculator(request):
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	return render(request, 'loan_calculator.html', {'lender': lender})


def apply_loan(request):
	if request.method == "POST":
		borrower = BorrowerProfile.objects.get(user=request.user)
		#loan_application = get_object_or_404(LoanApplication, id=loan_id, borrower__user=request.user)  

		lender_id = request.session.get('lender_id')
		try:
			lender = LenderProfile.objects.get(id=lender_id)
		except LenderProfile.DoesNotExist:
			messages.error(request, "Invalid lender selection.")
			return redirect('loan-calculator')

		loan_amount = float(request.POST.get('loan_amount'))
		loan_term = int(request.POST.get('loan_term'))
		collateral = request.POST.get('collateral')
		payment_plan = request.POST.get('payment_plan')

		# Get lender's interest rate
		interest_rate = float(lender.interest_rate) / 100  

		# Calculate total repayable amount
		total_repayable = loan_amount * (1 + (interest_rate * (loan_term / 12)))

		# Calculate monthly installment
		monthly_installment = total_repayable / loan_term

		# First payment can be same as monthly, unless there's a special case (e.g., upfront fees)
		first_payment = monthly_installment

		# Save loan application
		loan_application = LoanApplication.objects.create(
			borrower=borrower,
			lender=lender,
			loan_amount=loan_amount,
			loan_term=loan_term,
			#interest_rate=lender.interest_rate,  
			total_repayable=total_repayable,
			first_payment=first_payment,
			monthly_installment=monthly_installment,
			#collateral=collateral,
			#payment_plan=payment_plan,
			status='pending',
			date_applied=now(),

		)

		# Notify the lender about a new loan application
		Notification.objects.create(
			user=loan_application.lender.user,
			message=f"New loan application submitted by {loan_application.borrower.user.username} for R{loan_amount}.",
			category="loan_application",
			loan_application=loan_application
		)
		
		# Notify the lender
		#Notification.objects.create(
		#	user=loan_application.lender.user,
		#	message=f"New loan payment from {borrower.full_name}"
		#)
	

		# Notify the lender
		#Notification.objects.create(
		#	user=loan_application.lender,
		#	message=f"New loan payment from {borrower.full_name}"
		#)

		messages.success(request, "Loan application submitted successfully!")
		return redirect('borrower_index')

	return redirect('loan-calculator')




def calculate_loan(request):
	try:
		amount = Decimal(request.GET.get('amount', 0))
		term = int(request.GET.get('term', 3))  # Default to 3 months
		
		lender_id = request.session.get('lender_id')
		lender = LenderProfile.objects.get(id=lender_id)
		interest_rate = lender.interest_rate  

		# Ensure valid calculations
		if amount > 0 and term > 0:
			total_repayable = amount * (1 + (Decimal(interest_rate) / 100))
			monthly_installment = total_repayable / Decimal(term)

			first_repayment = monthly_installment + (total_repayable * Decimal('0.1'))  # Example logic
			next_repayments = monthly_installment

			return JsonResponse({
				"total_repayable": round(total_repayable, 2),
				"monthly_installment": round(monthly_installment, 2),
				"first_repayment": round(first_repayment, 2),
				"next_repayments": round(next_repayments, 2),
			})
		else:
			return JsonResponse({"error": "Invalid amount or term"}, status=400)
	
	except LenderProfile.DoesNotExist:
		return JsonResponse({"error": "Lender not found"}, status=404)
				
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)
	

# For Sidebar 
def apply_for_loan_list(request):
	lenders = LenderProfile.objects.all()
	return render(request, 'apply_loan_list.html', {'lenders': lenders})

@login_required
def my_loan_applications(request):
	loan_applications = LoanApplication.objects.filter(borrower=request.user.borrower).order_by('-date_applied')
	return render(request, 'my_loan_applications.html', {'loan_applications': loan_applications})



def my_active_loans(request):
	borrower = get_object_or_404(BorrowerProfile, user=request.user)
	active_loans = Loan.objects.filter(borrower=borrower, status='approved', outstanding_balance__gt=0)

	for loan in active_loans:
		total_paid = loan.total_repayable - loan.outstanding_balance
		loan.progress_percent = int((total_paid / loan.total_repayable) * 100)

			# Color coding
		if loan.progress_percent < 30:
			loan.progress_color = 'bg-danger'
		elif loan.progress_percent < 70:
			loan.progress_color = 'bg-warning'
		else:
			loan.progress_color = 'bg-success'

		# Next expected payment (assuming monthly schedule)
		#loan.next_payment_date = loan.date_created + timedelta(days=30 * loan.payments.count())
		loan.first_payment_date, loan.next_payment_date = calculate_first_and_next_payment_dates(loan)

		# Monthly Payment Status Timeline
		today = timezone.now()
		months_since_loan = (today.year - loan.date_created.year) * 12 + (today.month - loan.date_created.month) + 1

		adjusted_payment = calculate_adjusted_payment(loan)

		loan.monthly_status = []
		for i in range(months_since_loan):
			due_date = loan.date_created + timedelta(days=30 * i)
			next_month = due_date + timedelta(days=30)
			payment_made = loan.payments.filter(date_paid__gte=due_date, date_paid__lt=next_month).exists()

			loan.monthly_status.append({
				'month': due_date.strftime("%B %Y"),
				'status': 'Paid' if payment_made else 'Pending'
			})
		
	return render(request, 'my_active_loans.html', {
		'active_loans': active_loans,
		'adjusted_payment': adjusted_payment,

	})


def calculate_first_and_next_payment_dates(loan):
		pay_day = loan.borrower.pay_day or 1  # default to 1st if not set
		first_payment_date = loan.date_created.replace(day=pay_day)

		# If first payment date is before loan date, move to next month
		if first_payment_date < loan.date_created:
			first_payment_date = first_payment_date + timedelta(days=30)

		next_payment_date = first_payment_date + timedelta(days=30 * loan.payments.count())
		return first_payment_date, next_payment_date


def recalculate_with_interest(loan, months_missed):
	monthly_rate = loan.interest_rate / 100 / 12  # Convert annual interest to monthly decimal
	missed_debt = loan.monthly_installment * months_missed
	# Add compound interest to missed debt
	total_due = missed_debt * ((1 + monthly_rate) ** months_missed)
	return round(loan.monthly_installment + total_due, 2)


def recalculate_simple(loan, months_missed):
	return loan.monthly_installment * (1 + months_missed)


def calculate_adjusted_payment(loan):
	months_missed = calculate_missed_months(loan)

	if months_missed == 0:
		return loan.monthly_installment

	if loan.lender.recalculate_interest_on_missed:  # Assume this is a BooleanField on LenderProfile
		return recalculate_with_interest(loan, months_missed)
	else:
		return recalculate_simple(loan, months_missed)



#def mark_loan_approved_read(request):
#	if request.user.is_authenticated and request.user.is_borrower():
#		Notification.objects.filter(category="loan_approved", is_read=False).update(is_read=True)
#		return JsonResponse({'success': True})
#	return JsonResponse({'success': False}, status=400)


@csrf_exempt
def mark_loan_approved_read(request):
	if request.user.is_authenticated and request.method == "POST":
		Notification.objects.filter(user=request.user, category="loan_approved", is_read=False).update(is_read=True)
		return JsonResponse({"success": True})
	return JsonResponse({"success": False}, status=400)


def loan_application_success(request):
	return render(request, 'loan_application_success.html', {})


def my_loan_list(request):
	lender_id = request.session.get('lender_id')

	if request.user.is_authenticated:
		loans = Loan.objects.filter(borrower__user=request.user)  # Filter by logged-in borrower
	else:
		loans = Loan.objects.none()  # No loans if not logged in

	return render(request, 'my_loan_list.html', {'loans': loans})



class BorrowerNotificationListView(ListView):
	model = Notification
	template_name = 'borrower_notifications.html'
	context_object_name = 'notifications'

	def get_queryset(self):
		user = self.request.user
		filter_type = self.request.GET.get('filter', 'all')

		base_qs = Notification.objects.filter(user=user)

		if filter_type == 'unread':
			return base_qs.filter(is_read=False)
		elif filter_type == 'read':
			return base_qs.filter(is_read=True)
		elif filter_type == 'approved':
			return base_qs.filter(category='loan_approved')
		elif filter_type == 'rejected':
			return base_qs.filter(category='loan_rejected')
		elif filter_type == 'pending':
			return base_qs.filter(category='loan_pending')

		return base_qs.order_by('-date_created')

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['current_filter'] = self.request.GET.get('filter', 'all')
		context['filters'] = [
			("All", "all"),
			("Unread", "unread"),
			("Read", "read"),
			("Approved", "approved"),
			("Rejected", "rejected"),
			("Pending", "pending"),
		]
		return context



@login_required
def loan_details(request, loan_id):
	loan = get_object_or_404(Loan, id=loan_id, borrower__user=request.user)
	payments = LoanPayment.objects.filter(loan=loan).order_by('-date_paid')
	adjusted_payment = calculate_adjusted_payment(loan)
	
	return render(request, 'loan_details.html', {
		'loan': loan,
		'payments': payments,
		'outstanding_balance': loan.outstanding_balance,
		'adjusted_payment': adjusted_payment,
	})



@login_required
def record_payment(request, loan_id):
	"""Allows a borrower to record a loan payment."""
	loan = get_object_or_404(Loan, id=loan_id, borrower__user=request.user)
	borrower = loan.borrower  # Get borrower from loan
	adjusted_payment = calculate_adjusted_payment(loan)

	if request.method == "POST":
		form = LoanPaymentForm(request.POST)

		if form.is_valid():
			payment = form.save(commit=False)
			payment.loan = loan
			payment.borrower = borrower

			

			#Remember to remove
			# Check missed payments
			missed_months = calculate_missed_months(loan)

			if missed_months > 0:
				if loan.lender.missed_payment_policy == 'recalculate':
					# Recalculate interest on missed months
					interest_multiplier = 1 + (loan.interest_rate / 100)
					loan.outstanding_balance *= interest_multiplier ** missed_months
					# Optionally recalculate monthly installment if needed
					loan.monthly_installment = loan.outstanding_balance / (loan.loan_term - loan.months_paid)
					loan.save()

				elif loan.lender.missed_payment_policy == 'double_payment':
					# Adjust current installment to reflect double (or more) payments
					payment.amount = loan.monthly_installment * (1 + missed_months)

			# Prevent overpayment
			if payment.amount > loan.outstanding_balance:
				messages.error(request, "You cannot pay more than the outstanding balance!")
				return redirect('record-payment', loan_id=loan.id)
			
			payment.save()
			# Update loan outstanding balance
			loan.update_outstanding_balance()

			messages.success(request, "Payment recorded successfully!")

			if loan.is_fully_paid():
				# Notify the lender for full payment
				Notification.objects.create(
					user=loan.lender.user,
					message=f"Borrower {loan.borrower.user.username} finished a loan payment with R{payment.amount} for Loan ID {loan.id}.",
					category="loan_payment",
					loan=loan
				)

			else:
				# Notify the lender
				Notification.objects.create(
					user=loan.lender.user,
					message=f"Borrower {loan.borrower.user.username} made a payment of R{payment.amount} for Loan ID {loan.id}.",
					category="loan_payment",
					loan=loan
				)

			return redirect('loan-details', loan_id=loan.id)
	else:
		form = LoanPaymentForm()

	return render(request, 'record_payment.html', 
		{'form': form, 'loan': loan, 'adjusted_payment': adjusted_payment})


def calculate_missed_months(loan):
	"""Detect how many months were missed based on first payment date and previous payment dates."""
	last_payment = loan.payments.order_by("-date_paid").first()
	today = date.today()

	if last_payment:
		expected_payment_date = last_payment.date_paid + relativedelta(months=1)
	else:
		expected_payment_date = loan.first_payment_date() 

	months_missed = (today.year - expected_payment_date.year) * 12 + (today.month - expected_payment_date.month)
	return max(0, months_missed)

@login_required
def borrower_payment_history(request):
	"""Shows all recorded payments for the logged-in borrower."""
	borrower = get_object_or_404(BorrowerProfile, user=request.user)
	loans = Loan.objects.filter(borrower=borrower).order_by("-date_created")

	for loan in loans:
		loan.remaining_months = loan.remaining_months()
		loan.payment_history = loan.payments.all().order_by("-date_paid")

	return render(request, 'borrower_payment_history.html', {'loans': loans})





# List of predefined vibrant colors for dashboard
COLORS = [
	"#FF5733",  # Vibrant Orange
	'#36ff33',
	#"#33FF57",  # Vibrant Green
	"#3357FF",  # Vibrant Blue
	'#3388ff',
	"#FF33A1",  # Pink
	"#FFC300",  # Bright Yellow
	#"#DAF7A6",  # Light Green
	'#085207',
	"#581845",  # Deep Purple
	"#C70039",  # Red
	"#900C3F",  # Dark Red
	"#2ECC71",  # Emerald Green
	"#3498DB",  # Sky Blue
	"#9B59B6",  # Amethyst
	"#F1C40F",  # Sunflower
	"#E67E22",  # Carrot Orange
	"#1ABC9C",  # Turquoise 

	# from Alenn.design
	'#46A094', # Turtles
	'#6BBD99',
	'#AECFA4',

	'#3B7197',
	'#4A8DB7',
	'#74BDE0',
	'#326789',
	'#78A6C8',
	'#E65C4F',
	'#0295A9',
	'#12ADC1',
	'#FDD037',
	'#244D61',
	'#5689C0',
	'#41436A',
	'#974063',
	'#F54768',
	'#FF9677',
	'#2E424D',
	'#5B8291',
]

# Randomly assign a color
def generate_random_color():
	return random.choice(COLORS)


from django.db.models import Avg

@login_required
def lender_details(request, lender_id):
	lender = get_object_or_404(LenderProfile, id=lender_id)
	borrower = request.user  # Ensure the user is logged in
	form = RatingForm()

	request.session['lender_id'] = lender_id
	#request.session['interest_rate'] = interest_rate

	# Check if the borrower already rated this lender
	existing_rating = Rating.objects.filter(lender=lender, borrower=borrower).first()

	# Fetch all ratings for the lender
	ratings = Rating.objects.filter(lender=lender)
	average_rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0  # Average rating (default to 0 if no ratings)

	if request.method == 'POST':
		form = RatingForm(request.POST)
		if form.is_valid():
			if existing_rating:
				# Update the existing rating
				existing_rating.rating = form.cleaned_data['rating']
				existing_rating.save()
				messages.success(request, "Your rating has been updated.")
			else:
				# Create a new rating
				rating = form.save(commit=False)
				rating.lender = lender
				rating.borrower = borrower
				rating.save()
				messages.success(request, "Your rating has been submitted.")
			return redirect('lender_details', lender_id=lender.id)

	context = {
		'lender': lender,
		'form': form,
		'existing_rating': existing_rating,
		'ratings': ratings,  # List of all ratings for this lender
		'average_rating': average_rating,  # Calculated average rating
		'rating_range': range(int(average_rating)),  # For displaying stars
	}
	return render(request, 'lender_details.html', context)



def rate_lender(request, lender_id):
	if request.method == 'POST':
		lender = get_object_or_404(LenderProfile, id=lender_id)
		rating = int(request.POST.get('rating', 0))
		if 1 <= rating <= 5:
			lender.rating = rating
			lender.save()
			messages.success(request, "Thank you for rating the lender!")
		else:
			messages.error(request, "Invalid rating. Please select a value between 1 and 5.")
		return redirect('lender_detail', lender_id=lender.id)




def loan_chart_data(request):
	user = request.user
	loans = Loan.objects.none()

	# Get loans depending on user role
	if hasattr(user, 'borrowerprofile'):
		loans = Loan.objects.filter(borrower=user.borrowerprofile)
	elif hasattr(user, 'lenderprofile'):
		loans = Loan.objects.filter(lender=user.lenderprofile)

	# Pie Chart Data: Loan status distribution
	status_data = loans.values('status').annotate(count=Count('id'))

	# Bar Chart Data: Total loan amounts issued per month
	bar_data = loans.extra(select={'month': "strftime('%%m', date_created)"}).values('month').annotate(total=Sum('amount'))

	# Area Chart: Sample balance over time (only for borrowers)
	area_data = []
	labels = []
	if hasattr(user, 'borrowerprofile'):
		sample_loan = loans.order_by('-date_created').first()
		if sample_loan:
			total_months = sample_loan.remaining_months() or 1
			monthly_reduction = sample_loan.total_repayable / total_months if total_months else Decimal('0.00')
			for i in range(total_months):
				labels.append(f'Month {i + 1}')
				balance = float(sample_loan.total_repayable - (monthly_reduction * i))
				area_data.append(round(balance, 2))

	return JsonResponse({
		"status_data": list(status_data),
		"bar_data": list(bar_data),
		"area_data": area_data,
		"area_labels": labels,
	})


@login_required
def monthly_repayments(request):
	borrower = request.user.borrower
	payments = LoanPayment.objects.filter(loan__borrower=borrower)

	monthly_totals = defaultdict(Decimal)

	for payment in payments:
		key = payment.date_paid.strftime('%Y-%m')  # e.g. '2025-04'
		monthly_totals[key] += payment.amount

	labels = sorted(monthly_totals.keys())
	data = [float(monthly_totals[month]) for month in labels]

	return JsonResponse({'labels': labels, 'data': data})


@login_required
def balance_over_time(request):
	borrower = request.user.borrower
	loans = Loan.objects.filter(borrower=borrower).order_by('date_created')

	timeline = {}
	for loan in loans:
		key = loan.date_created.strftime('%Y-%m')
		timeline[key] = float(loan.outstanding_balance)

	labels = sorted(timeline.keys())
	data = [timeline[label] for label in labels]

	return JsonResponse({'labels': labels, 'data': data})


@login_required
def paid_vs_outstanding(request):
	borrower = request.user.borrower
	loans = Loan.objects.filter(borrower=borrower)

	total_paid = Decimal(0)
	total_outstanding = Decimal(0)

	for loan in loans:
		total_paid += loan.total_paid()
		total_outstanding += loan.outstanding_balance

	return JsonResponse({
		'labels': ['Paid', 'Outstanding'],
		'data': [float(total_paid), float(total_outstanding)]
	})



def layout_sidenav_light(request):
	return render(request, 'layout_sidenav_light.html', {})


def layout_static(request):
	return render(request, 'layout_static.html', {})


#def login(request):
#	return render(request, 'login.html', {})

def password(request):
	return render(request, 'password.html', {})

#def register(request):
#	return render(request, 'borrower_index.html', {})


def tables(request):
	return render(request, 'tables.html', {})




