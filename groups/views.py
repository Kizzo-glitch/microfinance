from sqlite3 import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from datetime import date, timedelta
from django.db import models
from django.views import View
from django.contrib import messages
from borrowers.forms import BorrowerProfileForm
from borrowers.models import BorrowerProfile
from loans.models import LoanApplication, Loan, LoanPayment, Notification, Rating

from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum, Count
import uuid
from loans.utils import send_sms_smsportal
from .utils import is_group_admin, is_sub_admin, can_manage_operations
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse

from django.contrib.auth import get_user_model
from django.db import transaction, models as django_models
from django.http import HttpResponseForbidden
import re
from django.db.models import Q
import logging
logger = logging.getLogger(__name__)

from .models import (
	ActivityLog, BorrowerGroup, GroupActivity, GroupDocument, GroupMeeting, GroupMembership, GroupInvitation,
	GroupJoinRequest, GroupConstitution, GroupTypeSpecificSettings, MeetingAttendance
)
from borrowers.models import BorrowerProfile
from .forms import (
	BorrowerGroupForm, BorrowerMiniForm, GroupConstitutionForm, ActivationForm, GroupMeetingForm,
	GroupTypeSpecificSettingsForm, GroupJoinRequestForm, GroupInvitationForm,
	BorrowerGroupRegistrationForm, BorrowerJoinRequestForm, GroupAdminReviewForm
)
	 
User = get_user_model()

def group_landing(request):
	"""Public marketing page for Groups"""
	return render(request, 'group_landing.html')


def register_group_admin(request):
	if request.method == "POST":
		form = BorrowerGroupRegistrationForm(request.POST)
		if form.is_valid():
			user = form.save(commit=False)
			user.role = 'borrower' 
			user.save()

			login(request, user)
			messages.success(request, "Account created. Please complete your profile before creating a group.")
			return redirect('groups:group_borrower_profile')
		# If form is invalid, execution flows directly to the render() below
	else:
		form = BorrowerGroupRegistrationForm()
		
	# This must be outside the else block to catch invalid POST forms
	return render(request, 'register_group_admin.html', {'form': form})



def group_borrower_profile(request):
	# 1. Access Control Check
	if not request.user.is_authenticated or not getattr(request.user, 'is_borrower', False):
		messages.error(request, "You Must Be Logged In As A Borrower To Access That Page!!")
		return redirect('groups:groups_landing')

	user = request.user

	profile, created = BorrowerProfile.objects.get_or_create(user=user)

	# Force borrower to be a group admin
	if not profile.is_group_admin:
		profile.is_group_admin = True
		profile.save(update_fields=["is_group_admin"])

	# 3. Handle Form Submission
	if request.method == 'POST':
		form = BorrowerProfileForm(request.POST, instance=profile)
		if form.is_valid():
			updated_profile = form.save(commit=False)
			updated_profile.user = user
			updated_profile.save()
			messages.success(request, "Your Info Has Been Updated!!")
			return redirect('groups:group_admin_dashboard')
		else:
			print(form.errors)
	else:
		# Pre-fill initial data from the User model for the form fields
		initial_data = {
			'phone_number': getattr(user, 'phone_number', ''),
			'email_address': user.email,
			'full_name': f"{user.first_name} {user.last_name}".strip() if user.first_name else "",
		}
		form = BorrowerProfileForm(instance=profile, initial=initial_data)

	# 4. Gather Loan Statistics safely
	outstanding_loans = Loan.objects.filter(borrower=profile, outstanding_balance__gt=0).count()
	overdue_loans = Loan.objects.filter(borrower=profile, due_date__lt=date.today(), outstanding_balance__gt=0).count()
	total_debt = Loan.objects.filter(borrower=profile).aggregate(
		total=models.Sum('outstanding_balance')
	)['total'] or 0

	return render(request, "group_borrower_profile.html", {
		'form': form,
		'outstanding_loans': outstanding_loans,
		'overdue_loans': overdue_loans,
		'total_debt': total_debt,
	})


def group_borrower_profile2(request):
	if request.user.is_borrower:
		user = request.user
		current_user = BorrowerProfile.objects.get(user=request.user)
		try:
			current_user = BorrowerProfile.objects.get(user=request.user)
		except BorrowerProfile.DoesNotExist:
			messages.error(request, "Borrower profile not found.")
			return redirect('groups:group_landing')

		# Force borrower to be a group admin
		current_user.is_group_admin = True
		current_user.save(update_fields=["is_group_admin"])

		# Get original User Form (still editable for borrower details)
		form = BorrowerProfileForm(request.POST or None, instance=current_user)

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

		# Borrower's loan stats
		outstanding_loans = Loan.objects.filter(
			borrower=current_user, outstanding_balance__gt=0
		).count()
		overdue_loans = Loan.objects.filter(
			borrower=current_user, due_date__lt=date.today(), outstanding_balance__gt=0
		).count()
		total_debt = Loan.objects.filter(borrower=current_user).aggregate(
			total=models.Sum('outstanding_balance')
		)['total'] or 0
		
		if request.method == 'POST':
			# Pass the instance to update an existing profile or create a new one
			form = BorrowerProfileForm(request.POST, instance=current_user)
			if form.is_valid():
				profile = form.save(commit=False)
				profile.user = request.user
				profile.save()
				messages.success(request, "Your Info Has Been Updated!!")
				return redirect('groups:group_admin_dashboard')
			else:
				print(form.errors)
		else:
			# For a GET request, instantiate the form with initial data
			# and the instance (if it exists)
			form = BorrowerProfileForm(instance=current_user, initial=initial_data)

		return render(request, "group_borrower_profile.html", {
			'form': form,
			'outstanding_loans': outstanding_loans,
			'overdue_loans': overdue_loans,
			'total_debt': total_debt,
		})

	messages.error(request, "You Must Be Logged In To Access That Page!!")
	return redirect('groups:groups_landing')



def group_admin_login(request):
	if request.method == "POST":
		username = request.POST["username"]
		password = request.POST["password"]
		user = authenticate(request, username=username, password=password)

		if user is not None:
			try:
				borrower_profile = BorrowerProfile.objects.get(user=user)
			except BorrowerProfile.DoesNotExist:
				messages.error(request, "You must be a borrower to access Group Admin login.")
				return redirect("groups:group_admin_login")

			# ✅ Check if this borrower has "is_group_admin" flag set at registration
			if borrower_profile.is_group_admin:
				login(request, user)
				messages.success(request, "Welcome to your Group Admin Dashboard.")
				return redirect("groups:group_admin_dashboard")
			else:
				messages.error(request, "You are not authorized as a Group Admin.")
		else:
			messages.error(request, "Invalid login credentials.")

	return render(request, "login_group_admin.html")


def admin_logout(request):
	logout(request)
	messages.success(request, ('You have been logged out'))
	return redirect('groups:groups_landing') 



def group_admin_dashboard(request):
	"""
	Dashboard for group admins (the user must be admin of at least one group).
	Shows: groups administered, key metrics, pending items, recent activity.
	"""
	# assume BorrowerProfile accessible as request.user.borrower (your project used that)
	try:
		borrower_profile = request.user.borrower
	except Exception:
		# fallback if attribute name differs
		borrower_profile = getattr(request.user, 'borrower', None)

	# Groups where the current user is the admin
	administered_groups = BorrowerGroup.objects.filter(admin=borrower_profile).order_by('-created_at')

	# Aggregated metrics across administered groups
	group_ids = administered_groups.values_list('id', flat=True)

	# Members across those groups
	memberships = GroupMembership.objects.filter(group_id__in=group_ids)
	total_members = memberships.count()

	# Pending join requests across those groups
	pending_requests = GroupJoinRequest.objects.filter(group_id__in=group_ids, status='pending').order_by('-requested_at')
	pending_count = pending_requests.count()

	# Pending invitations
	pending_invitations = GroupInvitation.objects.filter(group_id__in=group_ids, status='pending').order_by('-sent_at')
	pending_invitations_count = pending_invitations.count()

	# Total savings across membership balances (if fields exist)
	total_savings_agg = memberships.aggregate(total_savings=Sum('current_savings_balance'))
	total_savings = total_savings_agg.get('total_savings') or 0

	# Active internal loans count (if your model exists) — keep safe if no attribute
	# Example: if you later add GroupLoan model with FK to BorrowerGroup, update this query
	active_group_loans = 0
	try:
		from .models import GroupLoan
		active_group_loans = GroupLoan.objects.filter(group_id__in=group_ids, status='active').count()
	except Exception:
		active_group_loans = 0

	# Recent activities example: last 10 join requests & invitations
	recent_join_requests = pending_requests[:8]
	recent_invitations = pending_invitations[:8]

	context = {
		'administered_groups': administered_groups,
		'total_groups': administered_groups.count(),
		'total_members': total_members,
		'pending_count': pending_count,
		'pending_invitations_count': pending_invitations_count,
		'total_savings': total_savings,
		'active_group_loans': active_group_loans,
		'recent_join_requests': recent_join_requests,
		'recent_invitations': recent_invitations,
	}
	return render(request, 'group_admin_dashboard.html', context)


@login_required
def manage_sub_admins(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id, admin=request.user.borrower)

	# Only admin can manage sub-admins
	members = group.memberships.select_related('borrower').all()
	current_sub_admins = group.sub_admins.all()

	if request.method == 'POST':
		selected_ids = request.POST.getlist('sub_admins')
		group.sub_admins.set(selected_ids)
		group.save()
		messages.success(request, "Sub-admins updated successfully.")
		return redirect('groups:group_detail', group.id)

	context = {
		'group': group,
		'members': members,
		'current_sub_admins': current_sub_admins
	}
	return render(request, 'manage_sub_admins.html', context)


def manage_members(request, group_id):
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

		return redirect('groups:manage_members', group_id=group.id)

	return render(request, 'manage_members.html', {
		'group': group,
		'members': members,
		'is_admin': current_member.role in ['admin', 'sub-admin']
	})

def manage_members2(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	
	# Permission check
	if not GroupMembership.objects.filter(group=group, borrower=request.user.borrower, role__in=['admin', 'sub-admin']).exists():
		messages.error(request, "You don’t have permission to manage members.")
		return redirect('borrowers:borrower_index')

	members = group.memberships.select_related('borrower__user')
	return render(request, 'admin_manage_members.html', {
		'group': group,
		'members': members,
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


# -----------------------------
# GROUP CREATION & MANAGEMENT
# -----------------------------
#@login_required
def group_list(request):
	borrower = request.user.borrower
	groups = BorrowerGroup.objects.filter(admin=borrower) | BorrowerGroup.objects.filter(memberships__borrower=borrower)
	groups = groups.distinct()
	return render(request, 'group_list.html', {'groups': groups})


@login_required
def group_create(request):
	borrower = request.user.borrower
	if request.method == 'POST':
		form = BorrowerGroupForm(request.POST, request.FILES)
		if form.is_valid():
			group = form.save(commit=False)
			group.admin = borrower
			group.status = 'draft'
			group.save()
			# Add admin as member automatically
			GroupMembership.objects.create(group=group, borrower=borrower, role='admin', status='active', verification_status='fully_verified')
			messages.success(request, "Group created successfully. You can now add constitution and settings.")
			return redirect('groups:group_detail', group.id)
	else:
		form = BorrowerGroupForm()
	return render(request, 'group_create.html', {'form': form})



def group_detail(request, pk):
	group = get_object_or_404(BorrowerGroup, pk=pk)
	type_settings = getattr(group, 'type_settings', None)
	join_requests = group.join_requests.all()

	pending_requests_count = group.join_requests.filter(status='pending').count()

	# Allow only group admin to edit type-specific settings
	can_edit = request.user == group.admin.full_name  # assuming BorrowerProfile has related user

	if request.method == 'POST' and can_edit:
		form = GroupTypeSpecificSettingsForm(request.POST, instance=type_settings)
		if form.is_valid():
			settings_obj = form.save(commit=False)
			settings_obj.group = group
			settings_obj.save()
			messages.success(request, "Group type settings updated successfully.")
			return redirect('groups:group_detail', pk=group.pk)
	else:
		form = GroupTypeSpecificSettingsForm(instance=type_settings)

	return render(request, 'group_detail.html', {
		'group': group,
		'form': form,
		'can_edit': can_edit,
		'type_settings': type_settings,
		'join_requests': join_requests,
		'pending_requests_count': pending_requests_count,
	})


def group_members(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	members = GroupMembership.objects.filter(group=group).select_related('borrower')

	context = {
		'group': group,
		'members': members,
	}
	return render(request, 'group_members.html', context)



#@login_required
def group_edit(request, pk):
	group = get_object_or_404(BorrowerGroup, pk=pk, admin=request.user.borrower)
	if request.method == 'POST':
		form = BorrowerGroupForm(request.POST, request.FILES, instance=group)
		if form.is_valid():
			form.save()
			messages.success(request, "Group details updated successfully.")
			return redirect('groups:group_detail', group.id)
	else:
		form = BorrowerGroupForm(instance=group)
	return render(request, 'group_edit.html', {'form': form, 'group': group})


# -----------------------------
# GROUP CONSTITUTION 
# -----------------------------
#@login_required
def group_constitution(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	constitution, created = GroupConstitution.objects.get_or_create(group=group)
	if request.method == 'POST':
		form = GroupConstitutionForm(request.POST, instance=constitution)
		if form.is_valid():
			form.save()
			messages.success(request, "Constitution saved successfully.")
			return redirect('groups:group_detail', group.id)
	else:
		form = GroupConstitutionForm(instance=constitution)
	return render(request, 'group_constitution.html', {'group': group, 'form': form})


# -----------------------------
# GROUP SETTINGS
# -----------------------------

class GroupTypeSpecificSettingsView(View):
	"""
	Create or update group-type specific settings after group creation
	"""
	template_name = 'group_type_settings_form.html'

	def get(self, request, group_id):
		group = get_object_or_404(BorrowerGroup, id=group_id)

		# Retrieve or create settings for this group
		settings_instance, created = GroupTypeSpecificSettings.objects.get_or_create(group=group)

		form = GroupTypeSpecificSettingsForm(instance=settings_instance, group_type=group.group_type)
		context = {
			'group': group,
			'form': form,
			'created': created,
		}
		return render(request, self.template_name, context)

	def post(self, request, group_id):
		group = get_object_or_404(BorrowerGroup, id=group_id)
		settings_instance, created = GroupTypeSpecificSettings.objects.get_or_create(group=group)

		form = GroupTypeSpecificSettingsForm(request.POST, instance=settings_instance, group_type=group.group_type)
		if form.is_valid():
			form.save()
			messages.success(request, f"Settings for {group.name} have been successfully updated.")
			return redirect('groups:group_detail', group.id)

		messages.error(request, "Please correct the errors below.")
		return render(request, self.template_name, {'form': form, 'group': group})

@login_required
def group_type_settings(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	settings, created = GroupTypeSpecificSettings.objects.get_or_create(group=group)
	if request.method == 'POST':
		form = GroupTypeSpecificSettingsForm(request.POST, instance=settings)
		if form.is_valid():
			form.save()
			messages.success(request, "Group settings saved successfully.")
			return redirect('groups:group_detail', group.id)
	else:
		form = GroupTypeSpecificSettingsForm(instance=settings)
	return render(request, 'group_type_settings.html', {'group': group, 'form': form})


# -----------------------------
# JOIN REQUESTS & INVITATIONS
# -----------------------------

def send_group_invite(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	inviter = request.user.borrower  # BorrowerProfile of inviter

	if request.method == 'POST':
		form = GroupInvitationForm(request.POST)
		profile_form = BorrowerMiniForm(request.POST)

		if form.is_valid():
			invitation = form.save(commit=False)
			invitation.group = group
			invitation.invited_by = inviter

			# ✅ Handle borrower profile creation or linking
			borrower = None

			# If invitee already exists (matched by phone or email)
			phone = request.POST.get('invitee_phone')
			email = request.POST.get('invitee_email')

			existing_borrower = BorrowerProfile.objects.filter(
				models.Q(phone_number=phone) | models.Q(user__email=email)
			).first()

			if existing_borrower:
				if existing_borrower.user:
					messages.warning(request, f"{existing_borrower.full_name} already has an account and cannot be re-invited.")
					return redirect('groups:group_detail', group.id)
				borrower = existing_borrower
			else:
				# Create a new borrower profile if none exists
				if profile_form.is_valid():
					borrower = profile_form.save()
				else:
					messages.error(request, "Please complete invitee profile information correctly.")
					return render(request, 'invite_borrower.html', {
						'group': group,
						'form': form,
						'profile_form': profile_form,
					})

			# ✅ Assign borrower to invitation
			invitation.invitee = borrower
			invitation.invitee_name = borrower.full_name
			invitation.invitee_phone = borrower.phone_number
			invitation.invitee_email = borrower.user.email if borrower.user else email

			# ✅ Save invitation (auto-generates code)
			invitation.save()

			# ✅ Prepare and send SMS/email
			activation_url = request.build_absolute_uri(invitation.get_activation_url())
			sms_body = (
				f"Hi {invitation.invitee_name}, you’ve been invited to join {group.name}. "
				f"Use code {invitation.invitation_code} or click {activation_url}"
			)

			send_sms_smsportal(invitation.invitee_phone, sms_body)
			invitation.sms_sent = True
			invitation.sms_sent_at = timezone.now()
			"""
			if invitation.invitee_email:
				send_mail(
					subject=f"Invitation to join {group.name}",
					message=sms_body,
					from_email=settings.EMAIL_HOST_USER,
					recipient_list=[invitation.invitee_email],
				)
				"""
				

			invitation.save()
			messages.success(request, f"Invitation sent successfully! Code: {invitation.invitation_code}")
			return redirect('groups:group_detail', group.id)
		else:
			messages.error(request, "Please correct the errors below.")

	else:
		form = GroupInvitationForm()
		profile_form = BorrowerMiniForm()

	return render(request, 'invite_borrower.html', {
		'group': group,
		'form': form,
		'profile_form': profile_form,
	})


def activate_invite(request, code=None):
	# 1️⃣ Retrieve the invitation code
	invitation_code = code or request.POST.get('invitation_code')
	if not invitation_code:
		messages.error(request, "Missing invitation code.")
		return render(request, "activate_invite.html", {'form': ActivationForm()})

	invitation_code = invitation_code.strip().upper()

	# 2️⃣ Get the invitation
	invite = get_object_or_404(GroupInvitation, invitation_code=invitation_code, status='pending')
	borrower_profile = invite.invitee
	name_parts = invite.invitee_name.split()
	first_name = name_parts[0]
	last_name = name_parts[-1] if len(name_parts) > 1 else ""

	if request.method == "POST":
		form = ActivationForm(request.POST)
		if form.is_valid():
			username = form.cleaned_data['username']
			password = form.cleaned_data['password1']
			email = form.cleaned_data.get('email') or invite.invitee_email
			phone_number = form.cleaned_data.get('phone_number') or invite.invitee_phone

			# 🧠 Check if profile already linked to a user
			if borrower_profile.user:
				user = borrower_profile.user
				user.username = username
				user.email = email
				user.first_name = first_name
				user.last_name = last_name
				if hasattr(user, "phone_number"):
					user.phone_number = phone_number
				user.set_password(password)
				user.save()
			else:
				# ✅ Create a new user and link
				user = User.objects.create_user(
					username=username,
					email=email,
					password=password,
					first_name=first_name,
					last_name=last_name,
				)
				if hasattr(user, "phone_number"):
					user.phone_number = phone_number
					user.save()
				borrower_profile.user = user
				borrower_profile.activated_at = timezone.now()
				borrower_profile.save()

			# ✅ Mark invite accepted
			invite.status = 'accepted'
			invite.responded_at = timezone.now()
			invite.save()

			# Create group membership
			GroupMembership.objects.create(
				group=invite.group,
				borrower=borrower_profile,
				role='member',
				status='active',
				verification_status='identity_verified',
				joined_date=timezone.now()
			)

			# ✅ Log user in
			login(request, user)
			messages.success(request, f"Welcome {borrower_profile.full_name}, your account is now active.")
			return redirect("borrowers:borrower_index")

	else:
		form = ActivationForm(initial={
			'email': invite.invitee_email,
			'phone_number': invite.invitee_phone,
			'first_name': first_name,
			'last_name': last_name,
		})

	return render(request, "activate_invite.html", {
		"form": form,
		"invite": invite,
		"borrower_profile": borrower_profile
	})




def my_invitations(request):
	"""
	Show invitations sent by the current user
	"""
	inviter = request.user.borrower
	
	invitations = GroupInvitation.objects.filter(
		invited_by=inviter
	).select_related('group', 'invitee').order_by('-sent_at')
	
	return render(request, 'groups/my_invitations.html', {
		'invitations': invitations
	})



def has_borrower_profile(request, user_id):
	try:
		user = User.objects.get(pk=user_id)
		exists = BorrowerProfile.objects.filter(user=user).exists()
		return JsonResponse({'has_profile': exists})
	except User.DoesNotExist:
		return JsonResponse({'has_profile': False})



# -------------------------------------------------------
# 1️⃣ Borrower join requests
# -------------------------------------------------------
@login_required
def pending_join_requests(request):
	"""
	Shows a list of all pending join requests for the admin's groups.
	"""
	borrower_profile = request.user.borrower

	# Get groups managed by this admin (you might have sub_admins or main admin)
	admin_groups = BorrowerGroup.objects.filter(admin=borrower_profile)

	# Pending join requests for all their groups
	pending_requests = GroupJoinRequest.objects.filter(
		group__in=admin_groups, status='pending'
	).select_related('group', 'requester')

	context = {
		'pending_requests': pending_requests,
	}

	return render(request, 'pending_join_requests.html', context)


#@login_required
def approve_join_request(request, request_id):
	join_request = get_object_or_404(GroupJoinRequest, id=request_id, status='pending')
	borrower = join_request.requester
	group = join_request.group

	if not is_group_admin(request.user, group):
		messages.error(request, "Only the group admin can review join requests.")
		return redirect('groups:group_detail', group.id)

	# Add borrower to group membership
	group.memberships.create(borrower=borrower)
	join_request.status = 'approved'
	join_request.save()

	messages.success(request, f"{borrower} has been added to {group.name}.")
	return redirect('groups:pending_join_requests')


@login_required
def decline_join_request(request, request_id):
	join_request = get_object_or_404(GroupJoinRequest, id=request_id, status='pending')

	join_request.status = 'declined'
	join_request.save()

	messages.warning(request, f"Join request from {join_request.requester} has been declined.")
	return redirect('groups:pending_join_requests')

#@login_required
def invitation_detail(request, invitation_id):
	"""
	View detailed information about a specific invitation
	Only accessible by inviter or group admins
	"""
	invitation = get_object_or_404(
		GroupInvitation.objects.select_related(
			'group', 
			'invited_by', 
			'invitee', 
			'invitee__user'
		),
		id=invitation_id
	)
	
	# Check permissions - only inviter or group admins can view
	is_authorized = (
		invitation.invited_by == request.user.borrower or
		invitation.group.admin == request.user.borrower or
		request.user.borrower in invitation.group.sub_admins.all()
	)
	
	if not is_authorized:
		messages.error(request, "You don't have permission to view this invitation.")
		return redirect('groups:group_list')
	
	# Get endorsements if any
	endorsements = invitation.endorsed_by.all()
	endorsements_needed = max(0, invitation.endorsements_required - endorsements.count())
	
	# Check if invitation can be acted upon
	can_resend = invitation.status == 'pending' and not invitation.is_expired()
	can_withdraw = invitation.status == 'pending'
	can_extend = invitation.status == 'pending'
	
	context = {
		'invitation': invitation,
		'endorsements': endorsements,
		'endorsements_needed': endorsements_needed,
		'can_resend': can_resend,
		'can_withdraw': can_withdraw,
		'can_extend': can_extend,
	}
	
	return render(request, 'groups/invitation_detail.html', context)


#@login_required
def withdraw_invitation(request, invitation_id):
	"""
	Allow inviter to withdraw a pending invitation
	Requires POST method for security (CSRF protection)
	"""
	invitation = get_object_or_404(
		GroupInvitation,
		id=invitation_id,
		invited_by=request.user.borrower
	)
	
	if request.method == 'POST':
		if invitation.status == 'pending':
			with transaction.atomic():
				# Update invitation status
				invitation.status = 'withdrawn'
				invitation.responded_at = timezone.now()
				invitation.save()
				
				# Optional: Notify invitee that invitation was withdrawn
				if invitation.invitee_phone:
					try:
						sms_body = (
							f"Lumela {invitation.invitee_name}, "
							f"the invitation to join {invitation.group.name} has been withdrawn. "
							f"For more information, please contact {invitation.invited_by.full_name} at {invitation.invited_by.phone_number}."
						)
						send_sms_smsportal(invitation.invitee_phone, sms_body)
					except Exception as e:
						# Silent fail for SMS - don't block the withdrawal
						pass
				
				# Send email notification if email exists
				if invitation.invitee_email:
					try:
						email_body = f"""
						Lumela {invitation.invitee_name},
						
						The invitation to join {invitation.group.name} has been withdrawn by {invitation.invited_by.full_name}.
						
						If you have any questions, please contact:
						{invitation.invited_by.full_name}
						Phone: {invitation.invited_by.phone_number}
						
						Thank you.
						"""
						"""
						send_mail(
							subject=f"Invitation Withdrawn - {invitation.group.name}",
							message=email_body,
							from_email=settings.EMAIL_HOST_USER,
							recipient_list=[invitation.invitee_email],
							fail_silently=True
						)"""
					except Exception:
						pass
			
			messages.success(
				request, 
				f"Invitation to {invitation.invitee_name} withdrawn successfully."
			)
		else:
			messages.error(
				request, 
				f"Cannot withdraw invitation - it has been {invitation.get_status_display()}."
			)
		
		return redirect('groups:my_invitations')
	
	# GET request - show confirmation page
	context = {
		'invitation': invitation,
		'action': 'withdraw',
	}
	return render(request, 'groups/invitation_confirm_action.html', context)


#@login_required
def resend_invitation(request, invitation_id):
	"""
	Resend invitation notification (SMS/Email)
	Useful if invitee didn't receive the original notification
	"""
	invitation = get_object_or_404(
		GroupInvitation,
		id=invitation_id,
		invited_by=request.user.borrower
	)
	
	# Only pending invitations can be resent
	if invitation.status != 'pending':
		messages.error(request, "Can only resend pending invitations.")
		return redirect('groups:my_invitations')
	
	# Check if expired
	if invitation.is_expired():
		messages.error(
			request, 
			f"This invitation expired on {invitation.expires_at.strftime('%d %B %Y')}. "
			f"Please extend the expiry date first or create a new invitation."
		)
		return redirect('groups:extend_invitation', invitation_id=invitation.id)
	
	if request.method == 'POST':
		# Resend notifications
		try:
			activation_url = request.build_absolute_uri(invitation.get_activation_url())
			
			# Prepare SMS message
			sms_body = (
				f"Lumela {invitation.invitee_name}! "
				f"Reminder: You've been invited to join {invitation.group.name}. "
				f"Use code {invitation.invitation_code} or visit {activation_url} to activate your account. "
				f"Expires: {invitation.expires_at.strftime('%d %b %Y')}"
			)
			
			# Send SMS
			sms_sent = False
			try:
				send_sms_smsportal(invitation.invitee_phone, sms_body)
				invitation.sms_sent = True
				invitation.sms_sent_at = timezone.now()
				sms_sent = True
			except Exception as e:
				messages.warning(request, f"SMS failed to send: {str(e)}")
			
			# Send Email (if email provided)
			email_sent = False
			if invitation.invitee_email:
				try:
					email_body = f"""
					Lumela {invitation.invitee_name},
					
					This is a reminder that you have been invited to join {invitation.group.name} by {invitation.invited_by.full_name}.
					
					{invitation.personal_message if invitation.personal_message else ''}
					
					To activate your account, please visit:
					{activation_url}
					
					Or use invitation code: {invitation.invitation_code}
					
					This invitation expires on: {invitation.expires_at.strftime('%d %B %Y at %H:%M')}
					
					If you have any questions, please contact:
					{invitation.invited_by.full_name}
					Phone: {invitation.invited_by.phone_number}
					
					Thank you,
					{invitation.group.name}
					"""
					"""
					send_mail(
						subject=f"Reminder: Invitation to join {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[invitation.invitee_email],
						fail_silently=False
					)"""
					invitation.email_sent = True
					invitation.email_sent_at = timezone.now()
					email_sent = True
				except Exception as e:
					messages.warning(request, f"Email failed to send: {str(e)}")
			
			invitation.save()
			
			# Success message
			if sms_sent and email_sent:
				messages.success(
					request, 
					f"Invitation resent to {invitation.invitee_name} via SMS and Email."
				)
			elif sms_sent:
				messages.success(
					request, 
					f"Invitation resent to {invitation.invitee_name} via SMS."
				)
			elif email_sent:
				messages.success(
					request, 
					f"Invitation resent to {invitation.invitee_name} via Email."
				)
			else:
				messages.error(request, "Failed to resend invitation. Please try again.")
				
		except Exception as e:
			messages.error(request, f"Failed to resend invitation: {str(e)}")
		
		return redirect('groups:my_invitations')
	
	# GET request - show confirmation page
	context = {
		'invitation': invitation,
		'action': 'resend',
	}
	return render(request, 'groups/invitation_confirm_action.html', context)


#@login_required
def extend_invitation(request, invitation_id):
	"""
	Extend the expiry date of a pending invitation
	"""
	invitation = get_object_or_404(
		GroupInvitation,
		id=invitation_id,
		invited_by=request.user.borrower
	)
	
	if invitation.status != 'pending':
		messages.error(request, "Can only extend pending invitations.")
		return redirect('groups:my_invitations')
	
	if request.method == 'POST':
		days_to_extend = int(request.POST.get('days', 30))
		
		# Validate days (minimum 7, maximum 90)
		if days_to_extend < 7:
			days_to_extend = 7
		elif days_to_extend > 90:
			days_to_extend = 90
		
		with transaction.atomic():
			# Calculate new expiry date
			new_expiry = timezone.now() + timedelta(days=days_to_extend)
			old_expiry = invitation.expires_at
			
			# Update invitation
			invitation.expires_at = new_expiry
			invitation.save()
			
			# Notify invitee about extension
			if invitation.invitee_phone:
				try:
					activation_url = request.build_absolute_uri(invitation.get_activation_url())
					sms_body = (
						f"Lumela {invitation.invitee_name}, "
						f"your invitation to join {invitation.group.name} has been extended. "
						f"New expiry date: {new_expiry.strftime('%d %B %Y')}. "
						f"Code: {invitation.invitation_code}. "
						f"Visit: {activation_url}"
					)
					send_sms_smsportal(invitation.invitee_phone, sms_body)
				except Exception:
					pass
			
			# Send email notification
			if invitation.invitee_email:
				try:
					email_body = f"""
					Lumela {invitation.invitee_name},
					
					Your invitation to join {invitation.group.name} has been extended.
					
					Previous expiry date: {old_expiry.strftime('%d %B %Y')}
					New expiry date: {new_expiry.strftime('%d %B %Y')}
					
					You now have more time to activate your account.
					
					Invitation code: {invitation.invitation_code}
					Activation link: {request.build_absolute_uri(invitation.get_activation_url())}
					
					Thank you,
					{invitation.group.name}
					"""
					"""
					send_mail(
						subject=f"Invitation Extended - {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[invitation.invitee_email],
						fail_silently=True
					)"""
				except Exception:
					pass
		
		messages.success(
			request, 
			f"Invitation extended by {days_to_extend} days. "
			f"New expiry date: {new_expiry.strftime('%d %B %Y')}"
		)
		return redirect('groups:my_invitations')
	
	# GET request - show form
	context = {
		'invitation': invitation,
		'default_days': 30,
		'min_days': 7,
		'max_days': 90,
	}
	return render(request, 'groups/extend_invitation.html', context)


def cancel_invitation_activation(request, invitation_id):
	"""
	Allow invitee to decline/cancel an invitation
	Does not require login - invitee may not have account yet
	"""
	invitation = get_object_or_404(
		GroupInvitation,
		id=invitation_id,
		status='pending'
	)
	
	# Verify this is the invited person (by phone or existing profile)
	is_authorized = False
	
	if request.user.is_authenticated and hasattr(request.user, 'borrower'):
		# Logged in user - check if they're the invitee
		if invitation.invitee and invitation.invitee == request.user.borrower:
			is_authorized = True
	
	# For non-authenticated users, we'll trust the invitation_id access
	# (since it's a UUID-like code, it's relatively secure)
	# But we can add extra verification via POST with phone number
	
	if request.method == 'POST':
		# Optional: Verify phone number for non-authenticated users
		if not request.user.is_authenticated:
			phone_verification = request.POST.get('phone_number', '').strip()
			if phone_verification and phone_verification != invitation.invitee_phone:
				messages.error(request, "Phone number doesn't match. Cannot decline invitation.")
				return render(request, 'groups/decline_invitation.html', {
					'invitation': invitation,
					'require_phone_verification': True,
				})
		
		with transaction.atomic():
			# Update invitation status
			invitation.status = 'declined'
			invitation.responded_at = timezone.now()
			invitation.save()
			
			# Notify the inviter
			try:
				sms_body = (
					f"Lumela {invitation.invited_by.full_name}, "
					f"{invitation.invitee_name} has declined your invitation to join {invitation.group.name}."
				)
				send_sms_smsportal(invitation.invited_by.phone_number, sms_body)
			except Exception:
				pass
			
			# Send email to inviter
			if invitation.invited_by.email_address or (invitation.invited_by.user and invitation.invited_by.user.email):
				try:
					email = invitation.invited_by.email_address or invitation.invited_by.user.email
					email_body = f"""
					Lumela {invitation.invited_by.full_name},
					
					{invitation.invitee_name} has declined your invitation to join {invitation.group.name}.
					
					Invitation details:
					- Invited on: {invitation.sent_at.strftime('%d %B %Y')}
					- Code: {invitation.invitation_code}
					
					You may want to reach out to them directly to understand their decision.
					
					Thank you,
					{invitation.group.name}
					"""
					"""
					send_mail(
						subject=f"Invitation Declined - {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[email],
						fail_silently=True
					)"""
				except Exception:
					pass
		
		messages.info(request, "You have declined the invitation. The group admin has been notified.")
		
		# Redirect based on authentication status
		if request.user.is_authenticated:
			return redirect('borrowers:borrower_index')
		else:
			return render(request, 'groups/invitation_declined_success.html', {
				'invitation': invitation
			})
	
	# GET request - show confirmation form
	context = {
		'invitation': invitation,
		'require_phone_verification': not request.user.is_authenticated,
	}
	return render(request, 'groups/decline_invitation.html', context)






#@login_required
def group_invitations_list(request, group_id):
	"""
	View all invitations for a specific group
	Only accessible by group admins
	"""
	group = get_object_or_404(BorrowerGroup, id=group_id)
	
	# Check if user is admin or sub-admin
	is_admin = (
		group.admin == request.user.borrower or 
		request.user.borrower in group.sub_admins.all()
	)
	
	if not is_admin:
		messages.error(request, "Only group admins can view group invitations.")
		return redirect('groups:group_detail', group.id)
	
	# Get all invitations for this group
	invitations = GroupInvitation.objects.filter(
		group=group
	).select_related('invited_by', 'invitee').order_by('-sent_at')
	
	# Filter by status if requested
	status_filter = request.GET.get('status', '')
	if status_filter:
		invitations = invitations.filter(status=status_filter)
	
	# Search functionality
	search_query = request.GET.get('search', '').strip()
	if search_query:
		invitations = invitations.filter(
			models.Q(invitee_name__icontains=search_query) |
			models.Q(invitee_phone__icontains=search_query) |
			models.Q(invitee_email__icontains=search_query) |
			models.Q(invitation_code__icontains=search_query)
		)
	
	# Calculate statistics
	stats = {
		'total': GroupInvitation.objects.filter(group=group).count(),
		'pending': GroupInvitation.objects.filter(group=group, status='pending').count(),
		'accepted': GroupInvitation.objects.filter(group=group, status='accepted').count(),
		'declined': GroupInvitation.objects.filter(group=group, status='declined').count(),
		'expired': GroupInvitation.objects.filter(group=group, status='expired').count(),
		'withdrawn': GroupInvitation.objects.filter(group=group, status='withdrawn').count(),
	}
	
	context = {
		'group': group,
		'invitations': invitations,
		'stats': stats,
		'status_filter': status_filter,
		'search_query': search_query,
	}
	
	return render(request, 'groups/group_invitations.html', context)



# -------------------------------------------------------
# 2️⃣ Group admin reviews and manages requests
# -------------------------------------------------------
#@login_required
def review_join_request(request, request_id):
	join_request = get_object_or_404(GroupJoinRequest, id=request_id)
	group = join_request.group

	# Only admin can access
	if not is_group_admin(request.user, group):
		messages.error(request, "Only the group admin can review join requests.")
		return redirect('groups:group_detail', group.id)

	if request.method == 'POST':
		form = GroupAdminReviewForm(request.POST, instance=join_request)
		if form.is_valid():
			review = form.save(commit=False)

			# Auto-handle decision date and notify applicant
			if review.status in ['approved', 'rejected']:
				review.decision_date = timezone.now()

			review.save()
			form.save_m2m()

			messages.success(request, f"Join request for {join_request.requester.full_name} updated successfully.")
			return redirect('groups:group_admin_dashboard', group_id=group.id)
	else:
		form = GroupAdminReviewForm(instance=join_request)

	return render(request, 'admin_review_join_request.html', {'form': form, 'join_request': join_request, 'group': group})




def create_meeting(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)

	if request.method == "POST":
		form = GroupMeetingForm(request.POST, request.FILES)
		if form.is_valid():
			meeting = form.save(commit=False)
			meeting.group = group
			meeting.created_by = request.user
			meeting.save()

			# Log event
			ActivityLog.objects.create(
				group=group,
				actor=request.user,
				action="meeting_created",
				details=f"Created meeting: {meeting.title}"
			)

			# Auto-create attendance records
			for member in group.members.all():
				MeetingAttendance.objects.get_or_create(meeting=meeting, member=member)

			return redirect("group_meetings", group_id=group.id)
	else:
		form = GroupMeetingForm()

	return render(request, "create_meeting.html", {
		"group": group,
		"form": form,
	})



def group_meetings(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	meetings = group.meetings.order_by("-date", "-created_at")

	return render(request, "groups/meetings/meeting_list.html", {
		"group": group,
		"meetings": meetings,
	})


def meeting_detail(request, group_id, meeting_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	meeting = get_object_or_404(GroupMeeting, id=meeting_id, group=group)

	attendance = meeting.attendance.select_related("member", "member__user")

	return render(request, "groups/meetings/meeting_detail.html", {
		"group": group,
		"meeting": meeting,
		"attendance": attendance,
	})



def update_attendance(request, group_id, meeting_id):
	meeting = get_object_or_404(GroupMeeting, id=meeting_id, group__id=group_id)

	if request.method == "POST":
		for key, value in request.POST.items():
			if key.startswith("present_"):
				attendance_id = key.split("_")[1]
				record = MeetingAttendance.objects.get(id=attendance_id)
				record.was_present = (value == "on")
				record.save()

		ActivityLog.objects.create(
			group=meeting.group,
			actor=request.user,
			action="attendance_updated",
			details=f"Updated attendance for meeting: {meeting.title}"
		)

	return redirect("meeting_detail", group_id=group_id, meeting_id=meeting_id)





'''@login_required
def explore_groups(request):
	"""Lenders see list of groups"""
	if not hasattr(request.user, 'lenderprofile'):
		return redirect('groups_landing')
	groups = BorrowerGroup.objects.filter(is_verified=True)
	return render(request, 'groups_explore.html', {'groups': groups})


def group_detail(request, group_id):
	"""Public group detail (basic info)"""
	group = get_object_or_404(BorrowerGroup, id=group_id)
	return render(request, 'group_detail.html', {'group': group})'''

'''@login_required
def join_group_by_code(request, code):
	
	invite = get_object_or_404(GroupInvite, code=code, is_used=False)
	borrower = request.user.borrowerprofile
	invite.group.members.add(borrower)
	invite.is_used = True
	invite.save()
	return redirect('my_group_dashboard')



# -------------------------------------------------------
# 1️⃣ Borrower applies to join a group
# -------------------------------------------------------
@login_required
def apply_to_join_group(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	borrower = request.user.borrower

	# Check if they already applied
	existing_request = GroupJoinRequest.objects.filter(group=group, requester=borrower, status__in=['pending', 'interview_scheduled', 'voting']).first()
	if existing_request:
		messages.warning(request, f"You already have a pending request to join {group.name}.")
		return redirect('group_detail', group_id=group.id)

	if request.method == 'POST':
		form = BorrowerJoinRequestForm(request.POST)
		if form.is_valid():
			join_request = form.save(commit=False)
			join_request.requester = borrower
			join_request.group = group
			join_request.status = 'pending'
			join_request.save()

			messages.success(request, f"Your request to join {group.name} has been submitted for review.")
			return redirect('groups:group_detail', group_id=group.id)
	else:
		form = BorrowerJoinRequestForm(initial={'group': group})

	return render(request, 'borrower_join_request_form.html', {'form': form, 'group': group})


def activate_invite(request, code):
	invite = get_object_or_404(GroupInvite, code=code, is_used=False)
	borrower_profile = invite.group.members.filter(email=invite.email).first()

	if request.method == "POST":
		form = ActivationForm(request.POST)
		if form.is_valid():
			username = form.cleaned_data['username']
			password = form.cleaned_data['password1']

			# ✅ Create User account with borrower role
			user = User.objects.create_user(
				username=username,
				email=invite.email,
				password=password
			)
			user.role = "borrower"   # if you have a Profile model
			user.profile.save()

			# ✅ Link user to borrower profile
			borrower_profile.user = user
			borrower_profile.save()

			invite.is_used = True
			invite.save()

			login(request, user)
			messages.success(request, "Your borrower account has been activated and linked to the group.")
			return redirect("borrower_index")
	else:
		form = ActivationForm()

	return render(request, "activate_invite.html", {"form": form, "invite": invite})'''

