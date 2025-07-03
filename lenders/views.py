from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import LenderInfoForm, LoanApplicationStatusForm, LoanStatusForm, LenderDocumentsForm
from .models import LenderProfile, LenderDocs
from django.contrib import messages
from loans.models import Notification, LoanApplication, Loan, LoanPayment
from django.http import JsonResponse
from borrowers.models import BorrowerProfile, BorrowerDocs
from loans.models import LoanApplication

from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse

from django.views.generic import ListView, UpdateView, DetailView
from decimal import Decimal
from datetime import timedelta
from datetime import date
from django.db import models

from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.db.models.functions import TruncMonth

import json
import calendar


from django.utils.timezone import now
from datetime import timedelta

from django.http import JsonResponse
from collections import OrderedDict

from loans.utils import get_loans_by_risk_category, send_sms_smsportal

from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings


from django.template.loader import render_to_string
from django.core.mail import send_mail, EmailMultiAlternatives, EmailMessage
from django.http import HttpResponse







def lender_index(request):
	if request.user.is_authenticated and request.user.is_lender():
		lender = request.user.lender
		loans = Loan.objects.filter(lender=lender)

		# Total Loans Disbursed
		total_loans_disbursed = loans.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')		
		total_recovered = LoanPayment.objects.filter(loan__in=loans).aggregate(Sum('amount'))['amount__sum'] or 0
		
		# Pull loan applications by this lender
		loan_applications = LoanApplication.objects.filter(lender=lender, is_deleted=False)
		deleted_loan_applications = LoanApplication.objects.filter(lender=lender, is_deleted=True)

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
		deleted_loan_applications = deleted_loan_applications.count()	

		high_risk_count = get_loans_by_risk_category("high").count()
		mid_risk_count = get_loans_by_risk_category("mid").count()
		late_payers_count = get_loans_by_risk_category("late").count()

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
			'deleted_loan_applications': deleted_loan_applications,

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


def upload_lender_docs(request):
	lender = request.user.lender

	if request.method == 'POST':
		form = LenderDocumentsForm(request.POST, request.FILES)
		if form.is_valid():
			
			doc_map = {
				'id_proof': 'ID Proof',
				'bank_statement': 'Bank Statement',
				'payslip': 'Payslip',
				'chief_letter': 'Chief Letter',
			}

			for doc_type in form.cleaned_data:
				file = form.cleaned_data[doc_type]
				if file:
					LenderDocs.objects.update_or_create(
						lender=lender,
						document_type=doc_type,
						file=file
					)
			return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/lenders/view_lender_documents/'})
		else:
			return JsonResponse({'error': form.errors})
	else:
		form = LenderDocumentsForm()

	return render(request, 'upload_lender_documents.html', {'form': form})


@login_required
def view_lender_documents(request):
	lender = request.user.lender
	lender_documents = LenderDocs.objects.filter(lender=lender)
	
	# Group documents by type for template rendering
	docs_by_type = {doc.document_type: doc for doc in lender_documents}

	return render(request, 'view_lender_documents.html', {'lender_documents': docs_by_type})


@login_required
def download_lender_document(request, document_type):
	try:
		lender_documents = LenderDocs.objects.filter(borrower=request.user.borrower)
	except LenderDocs.DoesNotExist:
		raise Http404("No documents found.")

	document_file = getattr(lender_documents, document_type, None)
	if not document_file:
		raise Http404("Requested document does not exist.")

	file_path = document_file.path
	if not os.path.exists(file_path):
		raise Http404("File not found.")

	with open(file_path, 'rb') as f:
		response = HttpResponse(f.read(), content_type="application/octet-stream")
		response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
		return response


def update_lender_documents(request):
	lender = get_object_or_404(LenderProfile, user=request.user)

	if request.method == 'POST':
		for doc_type in LenderDocs.DOCUMENT_TYPES:
			file = request.FILES.get(doc_type[0])
			if file:
				LenderDocs.objects.update_or_create(
					lender=lender,
					document_type=doc_type[0],
					defaults={'file': file}
				)
		
		# Optional: Notify admin about document update
		Notification.objects.create(
			user=None,  # Assign to specific admin user if needed
			message=f"📄 Lender {lender.company_name} updated their business documents for verification.",
			category="lender_document_update",
		)

		messages.success(request, "Your documents were updated successfully.")
		return redirect('lender_dashboard')

	# Get existing documents for display
	existing_documents_qs = LenderDocs.objects.filter(lender=lender)
	existing_documents = {doc.document_type: doc for doc in existing_documents_qs}

	return render(request, 'update_lender_documents.html', {
		'existing_documents': existing_documents,
		'document_types': LenderDocs.DOCUMENT_TYPES
	})



@login_required
def lender_list(request):
	lenders = (LenderProfile.objects.filter(user__is_superuser=False, user__role='lender')
		.annotate(average_rating=Avg('ratings__rating')))


	return render(request, 'borrower_index.html', {'lenders': lenders})



@method_decorator(staff_member_required, name='dispatch')
class LenderVerificationListView(ListView):
	model = LenderProfile
	template_name = 'lender_verification_list.html'
	context_object_name = 'lenders'

	def get_queryset(self):
		return LenderProfile.objects.filter(verification_status='pending')


@method_decorator(staff_member_required, name='dispatch')
class LenderVerificationDetailView(UpdateView):
	model = LenderProfile
	fields = ['verification_status']
	template_name = 'lender_verification_detail.html'
	success_url = '/admin/lender-verifications/'  # Or reverse to this view

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		lender = self.get_object()
		context['lender_documents'] = lender.compliance_docs.all()
		return context


# Top-bar notifications
def mark_loan_application_notifications_read(request):
	Notification.objects.filter(category="loan_application", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})


def mark_loan_payment_notifications_read(request):
	Notification.objects.filter(category="loan_payment", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})

@login_required
def mark_pending_loan_update_notifications_read(request):
	if request.method == 'POST':
		Notification.objects.filter(
			Q(category="loan_update") | Q(category="document_update") | Q(category="loan_deleted"),
			user=request.user,
			is_read=False
		).update(is_read=True)
		return JsonResponse({'success': True})
	return JsonResponse({'success': False}, status=400)




# Side-bar notifications

# Remember to add this to individual clicks of notification
def mark_notification_read(request, notification_id):
	notification = get_object_or_404(Notification, id=notification_id, user=request.user)
	notification.is_read = True
	notification.save()

	# Optionally, redirect based on category
	if notification.category == 'loan_approved':
		return redirect('loan-detail', notification.loan_application.id)
	elif notification.category == 'loan_rejected':
		return redirect('loan-status')
	elif notification.category == 'loan_pending':
		return redirect('pending-loans')

	return redirect('notifications')


@require_POST
@login_required
def mark_all_notifications_read(request):
	request.user.notifications.filter(is_read=False).update(is_read=True)
	return JsonResponse({'status': 'success'})


class LenderNotificationListView(ListView):
	model = Notification
	template_name = 'lender_notifications.html'
	context_object_name = 'lender_notifications'

	def get_queryset(self):
		user = self.request.user
		filter_type = self.request.GET.get('filter', 'all')

		base_qs = Notification.objects.filter(user=user)

		if filter_type == 'unread':
			return base_qs.filter(is_read=False)
		elif filter_type == 'read':
			return base_qs.filter(is_read=True)
		elif filter_type == 'loan_update':
			return base_qs.filter(category='loan_update')
		elif filter_type == 'document_update':
			return base_qs.filter(category='document_update')
		elif filter_type == 'loan_deleted':
			return base_qs.filter(category='loan_deleted')
		elif filter_type == 'loan_application':
			return base_qs.filter(category='loan_application')
		elif filter_type == 'loan_payment':
			return base_qs.filter(category='loan_payment')


		return base_qs.order_by('-date_created')

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['current_filter'] = self.request.GET.get('filter', 'all')
		context['filters'] = [
			("All", "all"),
			("Unread", "unread"),
			("Read", "read"),

			("Loan Application", "loan_application"),
			("Loan Payment", "loan_payment"),

			("Loan Update", "loan_update"),
			("Documents Updated", "document_update"),
			("Loan Deleted", "loan_deleted"),
		]
		return context





def loan_application_success(request):
	return render(request, 'loan_application_success.html', {})


def my_loan_list(request):
	lender_id = request.session.get('lender_id')

	if request.user.is_authenticated:
		loans = Loan.objects.filter(borrower__user=request.user)  # Filter by logged-in borrower
	else:
		loans = Loan.objects.none()  # No loans if not logged in

	return render(request, 'my_loan_list.html', {'loans': loans})


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
		borrower_user = loan_application.borrower
		phone_number = borrower_user.phone_number

		# Check if status changed
		if loan_application.status != old_status:
			if loan_application.status == 'approved':
				# Only create Loan if not already linked
				if not loan_application.linked_loan:
					loan = Loan.objects.create(
						#borrower=loan_application.borrower,
						borrower=borrower_user,
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
					user=borrower_user.user,
					message=f"🎉 Your Loan application from {loan_application.lender.company_name} for R{loan_amount} has been approved.",
					category="loan_approved"
				)

				message = f"Hi {borrower_user.full_name}, your loan application for R{loan_amount} has been approved!"
				#send_sms(phone_number, message)
				send_sms_smsportal(phone_number, message)

			elif loan_application.status == 'rejected':
				reasons = loan_application.get_rejection_reasons_display()
				Notification.objects.create(
					user=borrower_user.user,
					message=f"❌ Your loan of R{loan_amount} from {loan_application.lender.company_name} was rejected. Reasons: {reasons}",
					#message=f"❌ Your loan of R{loan_amount} from {loan_application.lender.company_name} was rejected. Reason: {loan_application.status_reason}",
					category="loan_rejected"
				)
				
				message = f"Hi {borrower_user.full_name}, your loan of R{loan_amount} was rejected. Reasons: {reasons}."
				send_sms_smsportal(phone_number, message)

			elif loan_application.status == 'pending':
				reasons = loan_application.get_pending_reasons_display()
				Notification.objects.create(
					user=borrower_user.user,
					message=f"⏳ Your loan application from {loan_application.lender.company_name} is pending. Reasons: {loan_application.get_pending_reasons_display()}",
					#message=f"⏳ Your loan application from {loan_application.lender.company_name} is pending. Reason: {loan_application.status_reason}",
					category="loan_pending"
				)
				
				message = f"Hi {borrower_user.full_name}, your loan of R{loan_amount} is pending. Reasons: {reasons}."
				send_sms_smsportal(phone_number, message)

		loan_application.save()


		form.save_m2m()  # Save multi-select fields

		reasons = []
		if loan_application.status == 'rejected':
			reasons = loan_application.rejection_reasons
		elif loan_application.status == 'pending':
			reasons = loan_application.pending_reasons
		
		# Render the email content
		'''subject = f"Loan Application {loan_application.status.capitalize()}"
		from_email = settings.EMAIL_HOST_USER
		to_email = [borrower_user.email_address]

		message = render_to_string('loan_notification_letter.html', {
			'loan_application': loan_application,
			'status': loan_application.status,
			'reasons': reasons,
		})

		# Send as HTML email
		email = EmailMultiAlternatives(subject, '', from_email, to_email)
		email.attach_alternative(message, "text/html")
		email.send()'''

		return super().form_valid(form)

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		loan_application = self.get_object()
		borrower = loan_application.borrower

		documents = BorrowerDocs.objects.filter(borrower=borrower, loan_application=loan_application)

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

			'documents': documents,
			'document_fields': ['id_proof', 'bank_statement', 'payslip', 'chief_letter', 'business_address', 'customer_invoice', 'supplier_invoice', 'business_registration', 'tax_clearance', 'business_statements'],
		})

		return context

	def get_success_url(self):
		return reverse('loan-application-list')


def view_borrower_documents(request, loan_id):
	# Ensure lender only accesses their own loan applications
	loan_application = get_object_or_404(LoanApplication, id=loan_id, lender=request.user.lender)

	# Fetch documents linked to this loan application
	documents = BorrowerDocs.objects.filter(loan_application=loan_application)

	return render(request, 'view_borrower_documents.html', {
		'loan_application': loan_application,
		'documents': documents
	})


@login_required
def view_borrower_documents2(request, loan_id):
	loan = get_object_or_404(LoanApplication, id=loan_id, lender=request.user.lender)
	borrower = loan.borrower
	documents = BorrowerDocs.objects.filter(borrower=borrower).order_by('-upload_date')

		# List of field names to loop through in template
	document_fields = ['id_proof', 'bank_statement', 'payslip', 'chief_letter']

	return render(request, 'borrower_documents.html', {
		'loan': loan,
		'borrower': borrower,
		'documents': documents,
		'document_fields': document_fields,
	})



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
				'uploaded_documents': BorrowerDocs.objects.filter(user=loan.borrower.user),
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
	documents = BorrowerDocs.objects.filter(borrower__id__in=borrower_ids).select_related('borrower')

	return render(request, 'client_documents.html', {'documents': documents})


@login_required
def client_documents2(request):
	borrower = BorrowerProfile.objects.get(user=borrower)
	try:
		document = BorrowerDocs.objects.get(borrower=borrower)
	except BorrowerDocs.DoesNotExist:
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



