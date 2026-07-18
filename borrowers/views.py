import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from groups.forms import BorrowerJoinRequestForm, GroupJoinRequestForm
from lenders.models import LenderProfile
from loans.models import LoanApplication, Loan, LoanPayment, Notification, Rating
from micro.models import OTP

from .forms import (
	RatingForm, BorrowerProfileForm, LoanApplicationForm, BorrowerDocumentsForm, 
	LoanPaymentForm, OTPForm, EmploymentTypeForm, EmployedDocumentsForm, SelfEmployedDocumentsForm, 
	RegisteredBusinessDocumentsForm, ExpenseForm, DynamicExpenseForm
	)

import random

from django.contrib import messages

from .models import BorrowerProfile, BorrowerDocs, ExpenseAnalysis
from groups.models import BorrowerGroup, GroupActivity, GroupDocument, GroupInvitation, GroupJoinRequest, GroupMembership

from django.contrib.auth.decorators import login_required
from django.db.models import Avg

from django.http import JsonResponse, HttpResponse, Http404
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
from django.utils import timezone
from django.views.decorators.http import require_POST

import os
from django.conf import settings
from micro.utils import generate_otp 
from loans.utils import send_sms_smsportal
from django.core.mail import send_mail, EmailMultiAlternatives, EmailMessage

from .utils import handle_stage_navigation
from groups.utils import is_group_admin, is_sub_admin, can_manage_operations, is_group_member
from django.utils.safestring import mark_safe

from django.db.models.functions import TruncMonth




def borrower_profile(request):
	user = request.user
	if not request.user.is_authenticated or not request.user.role == 'borrower':
		messages.error(request, "You Must Be a logged in Borrower To Access That Page!!")
		return redirect('landing')

	# Get or create the BorrowerProfile instance for the current user
	try:
		current_user = BorrowerProfile.objects.get(user=request.user)
		# Pre-fill initial data from the User model for existing profiles
		initial_data = {
			'phone_number': user.phone_number,
			'email_address': user.email,
			'full_name': f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "",
		}
	except BorrowerProfile.DoesNotExist:
		# If no profile exists, create a new one and pre-fill fields
		current_user = None
		initial_data = {
			'phone_number': user.phone_number,
			'email_address': user.email,
			'full_name': f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "",
		}

	# Get borrower's outstanding and overdue loans
	outstanding_loans = Loan.objects.filter(borrower__user=request.user, outstanding_balance__gt=0).count()
	overdue_loans = Loan.objects.filter(borrower__user=request.user, due_date__lt=date.today(), outstanding_balance__gt=0).count()
	total_debt = Loan.objects.filter(borrower__user=request.user).aggregate(total=Sum('outstanding_balance'))['total'] or 0

	if request.method == 'POST':
		# Pass the instance to update an existing profile or create a new one
		form = BorrowerProfileForm(request.POST, request.FILES, instance=current_user)
		if form.is_valid():
			profile = form.save(commit=False)
			profile.user = request.user
			profile.save()
			messages.success(request, "Your Info Has Been Updated!!")
			return redirect('borrowers:borrower_index')
		else:
			print(form.errors)
	else:
		# For a GET request, instantiate the form with initial data
		# and the instance (if it exists)
		form = BorrowerProfileForm(instance=current_user, initial=initial_data)

	return render(request, "borrower_profile.html", {
		'form': form,
		'outstanding_loans': outstanding_loans,
		'overdue_loans': overdue_loans,
		'total_debt': total_debt,
	})



@login_required
def borrower_index(request):
	borrower = request.user.borrower
	lenders = (LenderProfile.objects.filter(user__is_superuser=False, user__role='lender')
		.annotate(average_rating=Avg('ratings__rating')))

	draft_app = LoanApplication.objects.filter(borrower=request.user.borrower, status="draft").last()

	# Current group membership
	membership = borrower.group_memberships.select_related('group').first()
	current_group = membership.group if membership else None

	# Pending join requests
	pending_requests = borrower.group_requests.filter(status='pending')

	# Available groups (exclude ones borrower already belongs to or has pending requests)
	joined_groups = BorrowerGroup.objects.filter(memberships__borrower=borrower)
	requested_groups = BorrowerGroup.objects.filter(join_requests__requester=borrower)
	available_groups = BorrowerGroup.objects.exclude(
		Q(id__in=joined_groups.values_list('id', flat=True)) |
		Q(id__in=requested_groups.values_list('id', flat=True))
	)
	# ✅ Pending Invitations
	pending_invitations = GroupInvitation.objects.filter(
		invitee_phone=borrower.phone_number,  
		status='pending'
	)

	for lender in lenders:
		lender.bg_color = generate_random_color()

	context = {
		'current_group': current_group,
		'pending_requests': pending_requests,
		'available_groups': available_groups,
		'lenders': lenders, 
		"draft_app": draft_app,
		'pending_invitations': pending_invitations,
		'joined_groups': joined_groups,
	}

	return render(request, 'borrower_index.html', context)


@login_required
def borrower_groups_dashboard(request):
	borrower = request.user.borrower

	# Current group membership
	membership = borrower.group_memberships.select_related('group').first()
	current_group = membership.group if membership else None

	# Pending join requests
	pending_requests = borrower.group_requests.filter(status='pending')

	# Available groups (exclude ones borrower already belongs to or has pending requests)
	joined_groups = BorrowerGroup.objects.filter(memberships__borrower=borrower)
	requested_groups = BorrowerGroup.objects.filter(join_requests__requester=borrower)
	available_groups = BorrowerGroup.objects.exclude(
		Q(id__in=joined_groups.values_list('id', flat=True)) |
		Q(id__in=requested_groups.values_list('id', flat=True))
	)

	# Current group membership
	membership = borrower.group_memberships.select_related('group').first()
	current_group = membership.group if membership else None

	# Pending join requests
	pending_requests = borrower.group_requests.filter(status='pending')

	# ✅ Pending Invitations
	pending_invitations = GroupInvitation.objects.filter(
		invitee_phone=borrower.phone_number,  # assuming borrowerprofile has phone_number
		status='pending'
	)

	context = {
		'current_group': current_group,
		'pending_requests': pending_requests,
		'available_groups': available_groups,
		
		'pending_invitations': pending_invitations,
		'joined_groups': joined_groups,
	}
	return render(request, 'borrower_groups_dashboard.html', context)


def borrower_group_detail(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)

	# Authorization: allow group members, admins/sub-admins, or platform admins
	user = request.user
	is_admin = is_group_admin(user, group)
	is_sub = is_sub_admin(user, group)
	member_related = False
	try:
		member_related = group.memberships.filter(borrower__user=user).exists() or group.admin == getattr(user, 'borrower', None)
	except Exception:
		member_related = False

	if not (is_admin or is_sub or member_related or user.is_superuser):
		messages.error(request, "You do not have permission to view that group.")
		return redirect('borrowers:borrower_index')

	# Members list
	memberships = group.memberships.select_related('borrower').order_by('-joined_date')[:100]  # limit
	members = [m for m in memberships]

	# Stats
	total_members = group.memberships.count()
	pending_invitations = group.invitations.filter(status='pending').count()
	pending_join_requests = group.join_requests.filter(status='pending').count()
	total_loans = group.total_loans_taken or 0
	total_amount_borrowed = group.total_amount_borrowed or 0
	total_amount_repaid = group.total_amount_repaid or 0

	# Recent activity: combine last invitations and join requests and show sorted by date
	inv_qs = group.invitations.all().values('id','invited_by_id','invitee_name','status','sent_at','sms_sent')
	jr_qs = group.join_requests.all().values('id','requester_id','reason_for_joining','status','requested_at')
	# unify into python list with label
	recent = []
	for i in group.invitations.order_by('-sent_at')[:10]:
		recent.append({
			'type': 'invitation',
			'actor': getattr(i.invited_by, 'full_name', str(i.invited_by)),
			'target': i.invitee_name or i.invitee_phone or i.invitee_email,
			'status': i.status,
			'created_at': i.sent_at,
			'obj': i,
		})
	for j in group.join_requests.order_by('-requested_at')[:10]:
		recent.append({
			'type': 'join_request',
			'actor': getattr(j.requester, 'full_name', str(j.requester)),
			'target': j.requester.full_name,
			'status': j.status,
			'created_at': j.requested_at,
			'obj': j,
		})
	# sort by created_at desc and limit
	recent_sorted = sorted(recent, key=lambda r: r['created_at'] or timezone.now(), reverse=True)[:12]

	# Member growth placeholder: monthly counts (example derived from joined_date)
	# build small synthetic series: last 6 months with counts (fallback to zeros)
	
	six_months_ago = now() - timezone.timedelta(days=180)
	monthly_qs = group.memberships.filter(joined_date__gte=six_months_ago).annotate(month=TruncMonth('joined_date')).values('month').annotate(count=Count('id')).order_by('month')
	# convert to dict month->count
	monthly_map = {item['month'].strftime("%b %Y"): item['count'] for item in monthly_qs}
	# create labels for last 6 months
	labels = []
	counts = []
	# Member growth per month
	growth_qs = (
		GroupMembership.objects.filter(group=group)
		.annotate(month=TruncMonth("joined_date"))
		.values("month")
		.annotate(total=Count("id"))
		.order_by("month")
	)
	labels = [x["month"].strftime("%b %Y") for x in growth_qs]
	data = [x["total"] for x in growth_qs]
	for i in range(5, -1, -1):
		m = (now() - timezone.timedelta(days=30*i)).replace(day=1)
		key = m.strftime("%b %Y")
		labels.append(key)
		counts.append(monthly_map.get(key, 0))

	# Chart data JSON-safe
	chart_data = {
		'labels': labels,
		'counts': counts
	}

	context = {
		'group': group,
		'memberships': memberships,
		'members': members,
		'is_admin': is_admin,
		'is_sub_admin': is_sub,
		'can_manage': can_manage_operations(user, group),
		'total_members': total_members,
		'pending_invitations': pending_invitations,
		'pending_join_requests': pending_join_requests,
		'total_loans': total_loans,
		'total_amount_borrowed': total_amount_borrowed,
		'total_amount_repaid': total_amount_repaid,
		'recent_activity': recent_sorted,
		'chart_data_json': mark_safe(json.dumps(chart_data)),

		"growth_labels": labels,
        "growth_data": data,
	}

	return render(request, 'borrower_group_detail.html', context)



@login_required
def borrower_join_group(request, group_id):
	borrower = request.user.borrower
	group = get_object_or_404(BorrowerGroup, id=group_id)

	if GroupMembership.objects.filter(group=group, borrower=borrower).exists():
		messages.info(request, "You are already a member of this group.")
		return redirect('borrowers:borrower_groups_dashboard')

	if GroupJoinRequest.objects.filter(group=group, requester=borrower, status='pending').exists():
		messages.warning(request, "You already have a pending request for this group.")
		return redirect('borrowers:borrower_groups_dashboard')

	if request.method == 'POST':
		form = BorrowerJoinRequestForm(request.POST)
		if form.is_valid():
			join_request = form.save(commit=False)
			join_request.group = group
			join_request.requester = borrower
			join_request.save()
			messages.success(request, "Your join request has been sent successfully.")
			return redirect('borrowers:borrower_groups_dashboard')
	else:
		form = BorrowerJoinRequestForm()

	return render(request, 'borrower_join_request_form.html', {'group': group, 'form': form})


def admin_manage_members(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	current_member = GroupMembership.objects.filter(group=group, borrower=request.user.borrower).first()

	# Permission check
	if not current_member or current_member.role not in ['admin', 'sub-admin']:
		messages.error(request, "You don’t have permission to manage members.")
		return redirect('borrowers:borrower_index')

	members = group.memberships.select_related('borrower__user')

	# Handle role actions
	if request.method == "POST":
		member_id = request.POST.get('member_id')
		action = request.POST.get('action')
		target_member = get_object_or_404(GroupMembership, id=member_id, group=group)

		if action == "promote" and target_member.role == "member":
			target_member.role = "sub-admin"
			target_member.save()
			GroupActivity.objects.create(
				group=group,
				actor=request.user.borrower,
				action="Promoted Member",
				details=f"{target_member.borrower.full_name} was promoted to Sub-Admin"
			)
			messages.success(request, f"{target_member.borrower.full_name} promoted to Sub-Admin.")

		elif action == "demote" and target_member.role == "sub-admin":
			target_member.role = "member"
			target_member.save()
			GroupActivity.objects.create(
				group=group,
				actor=request.user.borrower,
				action="Demoted Member",
				details=f"{target_member.borrower.full_name} was demoted to Member"
			)
			messages.info(request, f"{target_member.borrower.full_name} demoted to Member.")

		elif action == "remove":
			GroupActivity.objects.create(
				group=group,
				actor=request.user.borrower,
				action="Removed Member",
				details=f"{target_member.borrower.full_name} was removed from the group"
			)
			target_member.delete()
			messages.warning(request, f"{target_member.borrower.full_name} removed from the group.")

		else:
			messages.error(request, "Invalid action or role change not allowed.")

		return redirect('borrowers:admin_manage_members', group_id=group.id)

	return render(request, 'borrowers:admin_manage_members.html', {
		'group': group,
		'members': members,
		'is_admin': current_member.role in ['admin', 'sub-admin']
	})


def group_activity_log(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	logs = group.activities.all()

	action_filter = request.GET.get('action')
	if action_filter:
		logs = logs.filter(action__icontains=action_filter)

	return render(request, 'activity_log.html', {
		'group': group,
		'logs': logs,
	})

def group_documents(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	documents = group.documents.all()

	if request.method == 'POST':
		file = request.FILES.get('file')
		description = request.POST.get('description')
		if file:
			version = (group.documents.filter(file__icontains=file.name).count() + 1)
			GroupDocument.objects.create(
				group=group,
				uploaded_by=request.user.borrower,
				file=file,
				version=version,
				description=description,
			)
			messages.success(request, "Document uploaded successfully.")
			return redirect('groups:group_documents', group.id)

	return render(request, 'group_documents.html', {
		'group': group,
		'documents': documents,
	})


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


# For Sidebar 
def apply_for_loan_list(request):
	lenders = LenderProfile.objects.all()
	return render(request, 'apply_loan_list.html', {'lenders': lenders})


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
			return redirect('borrowers:lender_details', lender_id=lender.id)

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
		return redirect('borrowers:lender_details', lender_id=lender.id)



def send_otp(request):
	borrower = request.user.borrower
	phone_number = borrower.phone_number

	otp_code = generate_otp()

	# Save OTP
	OTP.objects.create(user=request.user, phone_number=phone_number, otp_code=otp_code)

	# Send SMS
	message = f"Hello {borrower.full_name}, your FedhaGrow OTP code is: {otp_code}"
	send_sms_smsportal(phone_number, message)
	
	# Render the email content
	subject = f"OTP Verification"
	from_email = settings.EMAIL_HOST_USER
	to_email = [borrower.email_address]

	#send_mail(subject, message, from_email, to_email, fail_silently=False, )

	return redirect('borrowers:verify_otp')



def verify_otp(request):
	if request.method == 'POST':
		otp_input = request.POST.get('otp')

		try:
			otp_entry = OTP.objects.filter(user=request.user, is_verified=False).latest('created_at')
		except OTP.DoesNotExist:
			messages.error(request, "No OTP found. Please try again.")
			return redirect('borrowers:send_otp')

		if otp_entry.is_expired():
			messages.error(request, "OTP expired. Please request a new one.")
			return redirect('borrowers:send_otp')

		if otp_entry.otp_code == otp_input:
			otp_entry.is_verified = True
			otp_entry.save()
			messages.success(request, "OTP verified successfully!")
			return redirect('borrowers:employment_type')  
		else:
			messages.error(request, "Invalid OTP. Please try again.")

	return render(request, 'verify_otp.html')



@login_required
def select_employment_type(request):
	profile = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)

	REQUIRED_DOCS = {
		"employed": [
			"Payslip (last 3 months)",
			"Bank statement (last 3 months)",
			"ID document",
			"Chief's Letter"
		],
		"self_employed": [
			"Proof of income (invoices/receipts)",
			"Bank statement (last 6 months)",
			"ID document",
			"Business Address",
			"Chief Letter",
			"Customer Invoice",
			"Supplier Invoice",
			"Tax Clearance Certificate"
		],
		"registered_business": [
			"Company registration certificate",
			"Tax clearance certificate",
			"Business Bank statement (last 6 months)",
			"Director’s ID document",
			"Business Address",
			"Chief Letter",
			"Customer Invoice",
			"Supplier Invoice",
		],
	}

	'''loan_app, _ = LoanApplication.objects.get_or_create(
		borrower=request.user.borrower,
		status="draft",
		defaults={"current_stage": "employment"}
	)'''

	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=profile,
		lender=lender,  
		status="draft",
		defaults={"current_stage": "employment"}
	)

	if request.method == "POST":
		#form = EmploymentTypeForm(request.POST, instance=loan_app)
		form = EmploymentTypeForm(request.POST, instance=profile)
		if form.is_valid():
			form.save()
			loan_app.employment_type = form.cleaned_data['employment_type']

		def next_stage(loan_app):
			# decide redirect dynamically
			if loan_app.employment_type == "employed":
				loan_app.current_stage = "documents"
				return "borrowers:upload_documents_employed"
			elif loan_app.employment_type == "self_employed":
				loan_app.current_stage = "documents"
				return "borrowers:upload_documents_self_employed"
			elif loan_app.employment_type == "registered_business":
				loan_app.current_stage = "documents"
				return "borrowers:upload_documents_registered_business"
			return "borrowers:borrower_index"

		response = handle_stage_navigation(request, form, loan_app, next_stage)
		if response:
			return response
	else:
		form = EmploymentTypeForm(instance=profile)

	return render(request, "employment_type.html", {
		"form": form,
		"required_docs": REQUIRED_DOCS,})


@login_required
def resume_application(request, app_id):
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	loan_app = LoanApplication.objects.get(id=app_id, borrower=request.user.borrower, lender=lender)

	if loan_app.current_stage == "employment":
		return redirect("borrowers:employment_type")

	elif loan_app.current_stage == "documents":
		if loan_app.borrower.employment_type == "employed":
			return redirect("borrowers:upload_documents_employed")
		elif loan_app.employment_type == "self_employed":
			return redirect("borrowers:upload_documents_self_employed")
		elif loan_app.employment_type == "registered_business":
			return redirect("borrowers:upload_documents_registered_business")
		else:
			# fallback if employment_type is missing/corrupt
			return redirect("borrowers:select_employment_type")

	elif loan_app.current_stage == "affordability":
		return redirect("borrowers:update_expenses")

	elif loan_app.current_stage == "loan_calculator":
		return redirect("borrowers:loan-calculator")

	elif loan_app.current_stage == "apply_loan":
		return redirect("borrowers:apply-loan")

	else:
		# unknown stage → fallback to dashboard
		return redirect("borrowers:borrower_index")




@login_required
def resume_application22(request, app_id):
	loan_app = LoanApplication.objects.get(id=app_id, borrower=request.user.borrower)

	if loan_app.current_stage == "employment":
		return redirect("borrowers:select_employment_type")
	elif loan_app.current_stage == "documents":
		return redirect("borrowers:upload_documents_employed")
	elif loan_app.current_stage == "affordability":
		return redirect("borrowers:update_expenses")
	elif loan_app.current_stage == "loan_calculator":
		return redirect("borrowers:loan-calculator")
	else:
		return redirect("borrowers:borrower_index")




@login_required
def delete_draft_application(request, pk):
	loan_app = get_object_or_404(LoanApplication, pk=pk, borrower=request.user.borrower)

	if loan_app.is_draft():  # ✅ Only drafts can be deleted
		loan_app.delete()
		messages.success(request, "Your draft loan application has been deleted successfully.")
	else:
		messages.error(request, "Only draft applications can be deleted.")

	return redirect('borrowers:borrower_index')




@login_required
def upload_documents_employed(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	
	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,  # ✅ This is correct
		status="draft",
		defaults={"current_stage": "documents"}
	)

	if request.method == 'POST':
		action = request.POST.get('action')  # "save_exit" or "save_continue"
		form = EmployedDocumentsForm(request.POST, request.FILES)

		if form.is_valid():
			for field_name in form.fields:
				file = form.cleaned_data.get(field_name)

				if file:
					BorrowerDocs.objects.update_or_create(
						borrower=borrower,
						loan_application=loan_app,
						document_type=field_name,
						defaults={'file': file}
					)

			# ✅ Handle Save & Exit
			if action == "save_exit":
				loan_app.current_stage = "documents"
				loan_app.save(update_fields=["current_stage"])
				messages.success(request, "Progress saved. You can resume later.")
				#return redirect("borrower_index")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/borrower_index/'})




			# ✅ Handle Save & Continue
			missing_docs = []
			for field_name in form.fields:
				has_uploaded = BorrowerDocs.objects.filter(
					borrower=borrower, 
					loan_application=loan_app, 
					document_type=field_name
				).exists()

				if not has_uploaded:
					missing_docs.append(field_name)

			if missing_docs:
				messages.error(request, f"Please upload required documents: {', '.join(missing_docs)}")
			else:
				loan_app.current_stage = "affordability"
				loan_app.save(update_fields=["current_stage"])
				#return redirect("update_expenses")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/update-expenses/'})

		else:
			messages.error(request, "Form error. Please check your uploads.")
	else:
		form = EmployedDocumentsForm()

	# Preload already uploaded docs
	#existing_docs = BorrowerDocs.objects.filter(borrower=borrower, loan_application=loan_app)
	#uploaded_map = {doc.document_type: doc for doc in existing_docs}

	docs_qs = BorrowerDocs.objects.filter(
		borrower=borrower,
		loan_application=loan_app
	)
	existing_docs = {doc.document_type: doc for doc in docs_qs}

	return render(request, 'upload_documents_employed.html', {
		'form': form,
		'existing_docs': existing_docs

	})







@login_required
def upload_documents_self_employed(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	
	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,  # ✅ This is correct
		status="draft",
		defaults={"current_stage": "documents"}
	)

	if request.method == 'POST':
		action = request.POST.get('action')  # "save_exit" or "save_continue"
		form = SelfEmployedDocumentsForm(request.POST, request.FILES)

		if form.is_valid():
			for field_name in form.fields:
				file = form.cleaned_data.get(field_name)

				if file:
					BorrowerDocs.objects.update_or_create(
						borrower=borrower,
						loan_application=loan_app,
						document_type=field_name,
						defaults={'file': file}
					)

			# ✅ Handle Save & Exit
			if action == "save_exit":
				loan_app.current_stage = "documents"
				loan_app.save(update_fields=["current_stage"])
				messages.success(request, "Progress saved. You can resume later.")
				#return redirect("borrower_index")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/borrower_index/'})


			# ✅ Handle Save & Continue
			missing_docs = []
			for field_name in form.fields:
				has_uploaded = BorrowerDocs.objects.filter(
					borrower=borrower, 
					loan_application=loan_app, 
					document_type=field_name
				).exists()

				if not has_uploaded:
					missing_docs.append(field_name)

			if missing_docs:
				messages.error(request, f"Please upload required documents: {', '.join(missing_docs)}")
			else:
				loan_app.current_stage = "affordability"
				loan_app.save(update_fields=["current_stage"])
				#return redirect("update_expenses")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/update-expenses/'})

		else:
			messages.error(request, "Form error. Please check your uploads.")
	else:
		form = SelfEmployedDocumentsForm()

	docs_qs = BorrowerDocs.objects.filter(
		borrower=borrower,
		loan_application=loan_app
	)
	existing_docs = {doc.document_type: doc for doc in docs_qs}

	return render(request, 'upload_documents_self_employed.html', {
		'form': form,
		'existing_docs': existing_docs

	})



@login_required
def upload_documents_registered_business(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	
	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,  # ✅ This is correct
		status="draft",
		defaults={"current_stage": "documents"}
	)

	if request.method == 'POST':
		action = request.POST.get('action')  # "save_exit" or "save_continue"
		form = RegisteredBusinessDocumentsForm(request.POST, request.FILES)

		if form.is_valid():
			for field_name in form.fields:
				file = form.cleaned_data.get(field_name)

				if file:
					BorrowerDocs.objects.update_or_create(
						borrower=borrower,
						loan_application=loan_app,
						document_type=field_name,
						defaults={'file': file}
					)

			# ✅ Handle Save & Exit
			if action == "save_exit":
				loan_app.current_stage = "documents"
				loan_app.save(update_fields=["current_stage"])
				messages.success(request, "Progress saved. You can resume later.")
				#return redirect("borrower_index")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/borrower_index/'})


			# ✅ Handle Save & Continue
			missing_docs = []
			for field_name in form.fields:
				has_uploaded = BorrowerDocs.objects.filter(
					borrower=borrower, 
					loan_application=loan_app, 
					document_type=field_name
				).exists()

				if not has_uploaded:
					missing_docs.append(field_name)

			if missing_docs:
				messages.error(request, f"Please upload required documents: {', '.join(missing_docs)}")
			else:
				loan_app.current_stage = "affordability"
				loan_app.save(update_fields=["current_stage"])
				#return redirect("update_expenses")
				return JsonResponse({'success': 'Documents uploaded successfully!', 'redirect_url': '/borrowers/update-expenses/'})

		else:
			messages.error(request, "Form error. Please check your uploads.")
	else:
		form = RegisteredBusinessDocumentsForm()

	docs_qs = BorrowerDocs.objects.filter(
		borrower=borrower,
		loan_application=loan_app
	)
	existing_docs = {doc.document_type: doc for doc in docs_qs}

	return render(request, 'upload_documents_registered_business.html', {
		'form': form,
		'existing_docs': existing_docs

	})



@login_required
def update_expenses(request):
	borrower = request.user.borrower
	employment_type = borrower.employment_type
	income = borrower.income

	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)

	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,  # ✅ This is correct
		status="draft",
		defaults={"current_stage": "affordability"}
	)

	if request.method == 'POST':
		form = DynamicExpenseForm(employment_type, data=request.POST or None)
		action = request.POST.get("action")

		if form.is_valid():
			for field_name, value in form.cleaned_data.items():
				if value:
					expense_type_label = field_name.replace('_', ' ').title()
					ExpenseAnalysis.objects.update_or_create(
						borrower=borrower,
						loan_application=loan_app,
						expense_type=expense_type_label,
						defaults={'amount': value}
					)

			# ✅ Handle Save & Exit
			if action == "save_exit":
				loan_app.current_stage = "affordability"
				loan_app.save(update_fields=["current_stage"])
				
				messages.success(request, "Expenses saved successfully.")
				return redirect('borrowers:borrower_index')

			# ✅ Handle Save & Continue
			elif action == "save_continue":
				loan_app.current_stage = "loan_calculator"
				loan_app.save(update_fields=["current_stage"])
				messages.success(request, "Expenses saved successfully.")
				return redirect('borrowers:loan-calculator')

		else:
			messages.error(request, "Please fill all required fields correctly.")

	else:
		form = DynamicExpenseForm(employment_type)

	return render(request, 'update_expenses.html', {
		'form': form,
		'employment_type': employment_type,
		'income': income
	})




@login_required
def loan_application(request):
	try:
		# Retrieve borrower profile
		borrower = BorrowerProfile.objects.get(user=request.user)

		 # Retrieve lender details from session
		lender_id = request.session.get('lender_id')
		interest_rate = request.session.get('interest_rate')

		if not lender_id: 
			messages.error(request, "No lender selected. Please start again.")
			return redirect('borrowers:borrower_index')

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
		return redirect('borrowers:borrower_profile')


'''@login_required
def loan_calculator2(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)

	# Get borrower's latest pending loan draft
	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,
		status="draft",   # keep drafts separate from "pending"
		defaults={"current_stage": "loan_calculator"}
	)

	if request.method == "POST":
		action = request.POST.get("action")

		if action == "save_exit":
			loan_app.current_stage = "loan_calculator"
			loan_app.save(update_fields=["current_stage"])
			return redirect('borrower_index')
			

		elif action == "save_continue":
			# Move forward to apply_loan page (review & confirm)
			loan_app.current_stage = "apply_loan"
			loan_app.save(update_fields=["current_stage"])
			return redirect('apply-loan')
			

	return render(request, "loan_calculator.html", {
		"lender": lender,
		"available_terms": lender.loan_terms or [],
		"loan_app": loan_app
	})



def loan_calculator3(request):
	lender_id = request.session.get('lender_id')
	lender = LenderProfile.objects.get(id=lender_id)
	return render(request, 'loan_calculator.html', {
			'lender': lender,
			'available_terms': lender.loan_terms or []
		})'''



@login_required
def loan_calculator(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = get_object_or_404(LenderProfile, id=lender_id)

	# Get or create draft for this borrower/lender
	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,
		status="draft",   # keep as draft until final submission
		defaults={"current_stage": "loan_calculator"}
	)

	BorrowerDocs.objects.filter(
		borrower=borrower, loan_application=None
	).update(loan_application=loan_app)

	ExpenseAnalysis.objects.filter(
		borrower=borrower, loan_application=None
	).update(loan_application=loan_app)

	if request.method == "POST":
		action = request.POST.get("action")

		# Always save loan values if provided
		loan_amount = request.POST.get("loan_amount")
		loan_term = request.POST.get("loan_term")

		if loan_amount and loan_term:
			loan_amount = Decimal(loan_amount)
			loan_term = int(loan_term)
			interest_rate = lender.interest_rate

			total_repayable = loan_amount * Decimal(1 + (interest_rate / 100))
			monthly_installment = total_repayable / loan_term
			first_payment = monthly_installment

			# ✅ Update draft with loan values
			loan_app.loan_amount = loan_amount
			loan_app.loan_term = loan_term
			loan_app.total_repayable = total_repayable
			loan_app.monthly_installment = monthly_installment
			loan_app.first_payment = first_payment
			loan_app.save()

		# Handle Save & Exit
		if action == "save_exit":
			loan_app.current_stage = "loan_calculator"
			loan_app.save(update_fields=["current_stage"])
			messages.success(request, "Loan calculator draft saved. You can resume later.")
			return redirect("borrowers:borrower_index")

		# Handle Save & Continue → move to apply_loan step
		elif action == "save_continue":
			loan_app.current_stage = "apply_loan"
			loan_app.save(update_fields=["current_stage"])
			return redirect("borrowers:apply-loan")

	return render(request, "loan_calculator.html", {
		"lender": lender,
		"available_terms": lender.loan_terms or [],
		"loan_app": loan_app
	})



def calculate_loan(request):
	try:
		lender_id = request.session.get('lender_id')
		lender = LenderProfile.objects.get(id=lender_id)

		amount = Decimal(request.GET.get('amount', 0))
		term = int(request.GET.get('term', 1))  

		# ✅ Ensure the term is one of the lender's terms
		if str(term) not in lender.loan_terms:
			return JsonResponse({"error": f"Invalid loan term. Allowed terms: {lender.loan_terms}"}, status=400)
		
		
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


@login_required
def apply_loan(request):
	borrower = request.user.borrower
	lender_id = request.session.get('lender_id')
	lender = get_object_or_404(LenderProfile, id=lender_id)

	loan_app, created = LoanApplication.objects.get_or_create(
		borrower=borrower,
		lender=lender,  # ✅ This is correct
		status="draft",
		defaults={"current_stage": "affordability"}
	)

	if not loan_app:
		messages.error(request, "No draft loan application found.")
		return redirect("borrowers:borrower_index")

	if request.method == "POST":
		# Before submission, check if borrower has any pending loan
		existing_loans = LoanApplication.objects.filter(
			borrower=borrower,
			status="pending"
		)
		if existing_loans.exists():
			messages.error(request, "You cannot apply for a new loan while you have a pending loan.")
			return redirect("borrowers:pending_loan")

		# ✅ Move draft to submitted
		loan_app.status = "pending"
		loan_app.date_applied = now()
		loan_app.current_stage = "submitted"
		loan_app.save(update_fields=["status", "date_applied", "current_stage"])

		# ✅ Notify the lender
		Notification.objects.create(
			user=loan_app.lender.user,
			message=f"New loan application submitted by {loan_app.borrower.full_name} for R{loan_app.loan_amount}.",
			category="loan_application",
			loan_application=loan_app
		)

		# ✅ Send borrower confirmation
		message = (
			f"Hello {borrower.full_name}, your Loan Application for R{loan_app.loan_amount} "
			f"was successfully submitted to {loan_app.lender.company_name}."
			f" {loan_app.lender.company_name} will review your application and let you know of it's status."
		)
		send_sms_smsportal(borrower.phone_number, message)

		# Render the email content
		subject = f"Application Submitted successfully"
		from_email = settings.EMAIL_HOST_USER
		to_email = [borrower.email_address]

		#send_mail(subject, message, from_email, to_email, fail_silently=False,)

		messages.success(request, f"Loan application submitted successfully to {lender.company_name}")
		return redirect("borrowers:borrower_index")


	BorrowerDocs.objects.filter(
		borrower=borrower,
		loan_application=None
	).update(loan_application=loan_app)

	ExpenseAnalysis.objects.filter(
		borrower=borrower,
		loan_application=None
	).update(loan_application=loan_app)

	# Always build affordability context for GET
	expenses = ExpenseAnalysis.objects.filter(loan_application=loan_app)
	total_expenses = sum(e.amount for e in expenses)
	monthly_income = borrower.income or 0
	installment = loan_app.monthly_installment or 0
	surplus_before = monthly_income - total_expenses
	surplus_after = surplus_before - installment

	affordability_index_before = (surplus_before / monthly_income * 100) if monthly_income else 0
	affordability_index_after = (surplus_after / monthly_income * 100) if monthly_income else 0

	context = {
		"loan_app": loan_app,
		"expenses": expenses,
		"total_expenses": total_expenses,
		"monthly_income": monthly_income,
		"installment": installment,
		"surplus_before": surplus_before,
		"surplus_after": surplus_after,
		"affordability_index_before": affordability_index_before,
		"affordability_index_after": affordability_index_after,
	}

	return render(request, "apply_loan.html", context)
	

@login_required
def view_documents(request):
	borrower = request.user.borrower
	documents = BorrowerDocs.objects.filter(borrower=borrower)
	
	# Group documents by type for template rendering
	docs_by_type = {doc.document_type: doc for doc in documents}

	return render(request, 'view_documents.html', {'documents': docs_by_type})


@login_required
def download_document(request, document_type):
	try:
		documents = BorrowerDocs.objects.filter(borrower=request.user.borrower)
	except BorrowerDocs.DoesNotExist:
		raise Http404("No documents found.")

	document_file = getattr(documents, document_type, None)
	if not document_file:
		raise Http404("Requested document does not exist.")

	file_path = document_file.path
	if not os.path.exists(file_path):
		raise Http404("File not found.")

	with open(file_path, 'rb') as f:
		response = HttpResponse(f.read(), content_type="application/octet-stream")
		response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
		return response


@login_required
def pending_loan_application(request):
	borrower = request.user.borrower
	pending_loan = LoanApplication.objects.filter(borrower=borrower, status='pending').first()

	return render(request, 'pending_loan.html', {
		'pending_loan': pending_loan
	})



def update_loan_application(request, application_id):
	application = get_object_or_404(LoanApplication, id=application_id, borrower__user=request.user)

	if application.status != 'pending':
		messages.error(request, "You can only update a pending loan application.")
		return redirect('borrowers:borrower_index')  

	if request.method == 'POST':
		form = LoanApplicationForm(request.POST, instance=application)
		if form.is_valid():
			updated_application = form.save(commit=False)

			# Recalculate repayment details
			interest_rate = float(application.lender.interest_rate) / 100
			loan_amount = float(updated_application.loan_amount)
			loan_term = updated_application.loan_term

			total_repayable = loan_amount * float((1 + (interest_rate * (loan_term / 12))))
			monthly_installment = total_repayable / loan_term

			# Update fields
			updated_application.total_repayable = total_repayable
			updated_application.monthly_installment = monthly_installment
			updated_application.first_payment = monthly_installment  # optional adjustment

			updated_application.save()

			# Send notification to lender
			Notification.objects.create(
				user=application.lender.user,
				message=f"✅ {application.borrower.full_name} updated their pending loan application.",
				category="loan_update",
				loan_application=application
			)

			messages.success(request, f"Your loan application to {application.lender.company_name} was successfully updated.")
			return redirect('borrowers:borrower_index')
	else:
		form = LoanApplicationForm(instance=application)

	return render(request, 'update_loan_application.html', {'form': form, 'application': application})


def update_documents(request, loan_id):
	borrower = request.user.borrower
	loan_application = get_object_or_404(LoanApplication, id=loan_id, borrower=borrower, status='pending')

	# Determine allowed document types based on income_type
	income_type = borrower.employment_type

	if income_type == "employed":
		allowed_documents = [
			('id_proof', 'ID Proof'),
			('bank_statement', 'Bank Statement'),
			('payslip', 'Payslip'),
			('chief_letter', 'Chief Letter'),
		]
	elif income_type == "self_employed_unregistered":
		allowed_documents = [
			('id_proof', 'ID Proof'),
			('bank_statement', 'Bank Statement'),
			('business_address', 'Business Address'),
			('chief_letter', 'Chief Letter'),
			('customer_invoice', 'Customer Invoice'),
			('supplier_invoice', 'Supplier Invoice'),
			('tax_clearance', 'Tax Clearance Certificate')
		]
	elif income_type == "registered_business":
		allowed_documents = [
			('id_proof', 'ID Proof'),
			('bank_statement', 'Bank Statement'),
			('business_statements', 'Business Bank Statement'),
			('business_address', 'Business Address'),
			('chief_letter', 'Chief Letter'),
			('customer_invoice', 'Customer Invoice'),
			('supplier_invoice', 'Supplier Invoice'),
			('tax_clearance', 'Tax Clearance Certificate')
		]
	else:
		allowed_documents = []  # fallback (no documents allowed)

	if request.method == 'POST':
		for doc_type in allowed_documents:
			file = request.FILES.get(doc_type[0])
			if file:
				BorrowerDocs.objects.update_or_create(
					borrower=borrower,
					loan_application=loan_application,
					document_type=doc_type[0],
					defaults={'file': file}
				)
		
		Notification.objects.create(
			user=loan_application.lender.user,
			message=f"📄 Borrower {borrower.full_name} updated loan documents for review.",
			category="document_update",
			loan_application=loan_application
		)
		messages.success(request, f"Loan Documents for {loan_application.lender.company_name} are updated successfully.")
		return redirect('borrowers:borrower_index')


	existing_documents_qs = BorrowerDocs.objects.filter(
		borrower=borrower,
		loan_application=loan_application
		)

	existing_documents = {}
	for doc in existing_documents_qs:
		# Only store the most recent one per type
		if doc.document_type not in existing_documents:
			existing_documents[doc.document_type] = doc


	return render(request, 'update_documents.html', {
		'loan_application': loan_application,
		'existing_documents': existing_documents,
		'document_types': allowed_documents  # Pass filtered list to template
	})


@login_required
def delete_loan_application(request, application_id):
	loan_application = get_object_or_404(LoanApplication, id=application_id, borrower__user=request.user, status='pending')

	# Unlink documents instead of deleting them
	BorrowerDocs.objects.filter(loan_application=loan_application).delete()
	#BorrowerDocs.objects.filter(loan_application=loan_application).update(loan_application=None)


	# Send notification to lender
	Notification.objects.create(
		user=loan_application.lender.user,
		message=f"❌ {loan_application.borrower.full_name} has deleted their pending loan application.",
		category="loan_deleted"
	)
	
	#loan_application.is_deleted = True
	#loan_application.save()
	loan_application.delete()
	
	messages.success(request, "Loan application deleted successfully.")

	return redirect('borrowers:borrower_index')





def calculate_first_and_next_payment_dates(loan):
		pay_day = loan.borrower.pay_day or 1  # default to 1st if not set
		first_payment = loan.date_created.replace(day=pay_day)

		# If first payment date is before loan date, move to next month
		if first_payment < loan.date_created:
			first_payment = first_payment + timedelta(days=30)

		next_payment = first_payment + timedelta(days=30 * loan.payments.count())
		return first_payment, next_payment



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



# Top-bar notifications
def mark_loan_approved_read(request):
	Notification.objects.filter(category="loan_approved", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})


def mark_loan_rejected_read(request):
	Notification.objects.filter(category="loan_rejected", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})


def mark_loan_pending_read(request):
	Notification.objects.filter(category="loan_pending", is_read=False).update(is_read=True)
	return JsonResponse({"success": True})



# Remember to add this to individual clicks of notification
def mark_notification_read(request, notification_id):
	notification = get_object_or_404(Notification, id=notification_id, user=request.user)
	notification.is_read = True
	notification.save()

	# Optionally, redirect based on category
	if notification.category == 'loan_approved':
		return redirect('borrowers:loan-detail', notification.loan_application.id)
	elif notification.category == 'loan_rejected':
		return redirect('borrowers:loan-status')
	elif notification.category == 'loan_pending':
		return redirect('borrowers:pending-loans')

	return redirect('borrowers:notifications')

@require_POST
@login_required
def mark_all_notifications_read(request):
	request.user.notifications.filter(is_read=False).update(is_read=True)
	return JsonResponse({'status': 'success'})


def loan_application_success(request):
	return render(request, 'loan_application_success.html', {})


def my_loan_list(request):
	lender_id = request.session.get('lender_id')

	if request.user.is_authenticated:
		loans = Loan.objects.filter(borrower__user=request.user)  # Filter by logged-in borrower
	else:
		loans = Loan.objects.none()  # No loans if not logged in

	return render(request, 'my_loan_list.html', {'loans': loans})


def my_active_loans(request):
	borrower = get_object_or_404(BorrowerProfile, user=request.user)
	active_loans = Loan.objects.filter(borrower=borrower, status='approved', outstanding_balance__gt=0)
	adjusted_payment = None  # Safe default

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
		loan.first_payment_day, loan.next_payment_date = calculate_first_and_next_payment_dates(loan)

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

@login_required
def my_loan_applications(request):
	loan_applications = LoanApplication.objects.filter(borrower=request.user.borrower).order_by('-date_applied')
	return render(request, 'my_loan_applications.html', {'loan_applications': loan_applications})


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
	borrower = loan.borrower 
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
				return redirect('borrowers:record-payment', loan_id=loan.id)
			
			payment.save()
			# Update loan outstanding balance
			loan.update_outstanding_balance()

			messages.success(request, "Payment recorded successfully!")

			if loan.is_fully_paid():
				# Notify the lender for full payment
				Notification.objects.create(
					user=loan.lender.user,
					message=f"✅ ✅ Borrower {loan.borrower.full_name} finished a loan payment with R{payment.amount} for Loan ID {loan.id}.",
					category="loan_payment",
					loan=loan
				)

			else:
				# Notify the lender
				Notification.objects.create(
					user=loan.lender.user,
					message=f"✅ Borrower {loan.borrower.full_name} made a payment of R{payment.amount} for Loan ID {loan.id}.",
					category="loan_payment",
					loan=loan
				)

			return redirect('borrowers:loan-details', loan_id=loan.id)
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
		expected_payment_date = loan.first_payment_date 

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

@login_required
def my_group(request):
	"""Borrower sees their group status"""
	borrower = request.user.borrower
	if hasattr(borrower, 'group'):
		group = borrower.group
		return render(request, 'my_group.html', {'group': group})
	else:
		return render(request, 'no_group.html')

"""
def join_group(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	borrower = request.user.borrower
	if GroupMembership.objects.filter(group=group, borrower=borrower).exists():
		messages.warning(request, "You are already a member of this group.")
		return redirect('groups:group_detail', group.id)

	if request.method == 'POST':
		form = GroupJoinRequestForm(request.POST)
		if form.is_valid():
			join_req = form.save(commit=False)
			join_req.group = group
			join_req.requester = borrower
			join_req.save()
			messages.success(request, "Join request submitted successfully.")
			return redirect('groups:group_detail', group.id)
	else:
		form = GroupJoinRequestForm()
	return render(request, 'join_group.html', {'group': group, 'form': form})
"""

'''
def join_group(request, token):
	invite = get_object_or_404(GroupInvite, token=token, is_used=False)
	if request.method == "POST":
		form = UserCreationForm(request.POST)
		if form.is_valid():
			user = form.save()
			GroupMembership.objects.create(user=user, group=invite.group, role='member')
			invite.is_used = True
			invite.save()
			messages.success(request, "Welcome to the group!")
			return redirect('login')
	else:
		form = UserCreationForm()

	return render(request, 'groups/join_group.html', {'form': form, 'group': invite.group})'''




def layout_sidenav_light(request):
	return render(request, 'layout_sidenav_light.html', {})


def layout_static(request):
	return render(request, 'layout_static.html', {})


def password(request):
	return render(request, 'password.html', {})


def tables(request):
	return render(request, 'tables.html', {})




