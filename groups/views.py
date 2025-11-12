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
	BorrowerGroup, GroupMembership, GroupInvitation,
	GroupJoinRequest, GroupConstitution, GroupTypeSpecificSettings
)
from borrowers.models import BorrowerProfile
from .forms import (
	BorrowerGroupForm, BorrowerMiniForm, GroupConstitutionForm, ActivationForm,
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
			user = form.save()
			login(request, user)
			messages.success(request, "Account created. Please complete your profile before creating a group.")
			return redirect('groups:group_borrower_profile') 
	else:
		form = BorrowerGroupRegistrationForm()
	return render(request, 'register_group_admin.html', {'form': form})



def group_borrower_profile(request):
	if request.user.is_borrower():
		user = request.user
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
	return redirect('groups:group_landing')




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


def group_admin_dashboard2(request):
	current_user = BorrowerProfile.objects.get(user__id=request.user.id)
	if current_user.is_group_admin:
		groups = BorrowerGroup.objects.filter(admin=request.user.borrower) | BorrowerGroup.objects.filter(sub_admins=request.user.borrower)
		return render(request, "group_admin_dashboard.html", {"groups": groups})
	else:
		messages.error(request, "You are not authorized as a Group Admin.")


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


def admin_manage_members(request, group_id):
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

# -----------------------------
# GROUP CREATION & MANAGEMENT
# -----------------------------
@login_required
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



@login_required
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
@login_required
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
			
			if invitation.invitee_email:
				send_mail(
					subject=f"Invitation to join {group.name}",
					message=sms_body,
					from_email=settings.EMAIL_HOST_USER,
					recipient_list=[invitation.invitee_email],
				)
				

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


"""
def send_group_invite(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id)
	inviter = getattr(request.user, 'borrower', None)
	if not inviter:
		# consistent permission response
		return HttpResponseForbidden("Only group members who are borrower profiles may invite.")

	# permission: allow group.admin (compare pks), group.sub_admins membership, or staff
	is_admin = (getattr(group, 'admin_id', None) == inviter.pk) or group.sub_admins.filter(pk=inviter.pk).exists() or request.user.is_staff
	if not is_admin:
		messages.error(request, "Only group admins can send invitations.")
		return redirect('groups:group_detail', group.id)

	if request.method == 'POST':
		invitation_form = GroupInvitationForm(request.POST)
		profile_form = BorrowerMiniForm(request.POST)

		invite_type = request.POST.get('invite_type', 'new')

		if invite_type == 'existing':
			if invitation_form.is_valid():
				raw_phone = invitation_form.cleaned_data['invitee_phone']
				phone = normalize_phone(raw_phone)

				# Lock potential matching rows to avoid races
				with transaction.atomic():
					existing_borrower = BorrowerProfile.objects.select_for_update().filter(phone_number=phone).first()

					if not existing_borrower:
						messages.error(request, f"No user found with phone number {raw_phone}.")
						return render(request, 'send_invite.html', {
							'group': group,
							'invitation_form': invitation_form,
							'profile_form': profile_form,
						})

					if GroupMembership.objects.filter(group=group, borrower=existing_borrower).exists():
						messages.warning(request, f"{existing_borrower.full_name} is already a member of this group.")
						return redirect('groups:group_detail', group.id)

					if GroupInvitation.objects.filter(group=group, invitee=existing_borrower, status='pending').exists():
						messages.warning(request, f"{existing_borrower.full_name} already has a pending invitation.")
						return redirect('groups:group_detail', group.id)

					invitation = invitation_form.save(commit=False)
					invitation.group = group
					invitation.invited_by = inviter
					invitation.invitee = existing_borrower
					invitation.invitee_name = existing_borrower.full_name
					invitation.invitee_phone = existing_borrower.phone_number
					# compute email clearly
					if existing_borrower.email_address:
						invitation.invitee_email = existing_borrower.email_address
					elif existing_borrower.user and existing_borrower.user.email:
						invitation.invitee_email = existing_borrower.user.email
					else:
						invitation.invitee_email = invitation_form.cleaned_data.get('invitee_email') or ''
					invitation.save()

				send_invitation_notification(request, invitation)
				messages.success(request, f"Invitation sent to {existing_borrower.full_name}!")
				return redirect('groups:group_detail', group.id)

		else:  # invite_type == 'new'
			if invitation_form.is_valid() and profile_form.is_valid():
				raw_phone = invitation_form.cleaned_data['invitee_phone']
				phone = normalize_phone(raw_phone)

				# create-or-reuse the borrower profile inside one transaction
				with transaction.atomic():
					# Try to lock existing record
					existing_borrower = BorrowerProfile.objects.select_for_update().filter(phone_number=phone).first()
					if existing_borrower:
						borrower_profile = existing_borrower
						# if it already has a user, prompt to use existing user flow
						if borrower_profile.user:
							messages.error(
								request,
								"A user with that phone already has an account. Use the existing user option."
							)
							return render(request, 'invite_borrower.html', {
								'group': group,
								'invitation_form': invitation_form,
								'profile_form': profile_form,
							})
						# update only allowed fields present on the model
						for field, value in profile_form.cleaned_data.items():
							if hasattr(borrower_profile, field) and field != 'user':
								setattr(borrower_profile, field, value)
						borrower_profile.save()
					else:
						borrower_profile = profile_form.save(commit=False)
						# set normalized phone if you maintain normalization
						borrower_profile.phone_number = phone
						# optional: record which admin created the profile, if this field exists
						if hasattr(borrower_profile, 'created_by_admin'):
							borrower_profile.created_by_admin = inviter
						borrower_profile.save()

					# ensure no existing pending invitation for same person/group
					if GroupInvitation.objects.filter(group=group, invitee=borrower_profile, status='pending').exists():
						messages.warning(request, f"{borrower_profile.full_name} already has a pending invitation.")
						return redirect('groups:group_detail', group.id)

					invitation = invitation_form.save(commit=False)
					invitation.group = group
					invitation.invited_by = inviter
					invitation.invitee = borrower_profile
					# ensure we store normalized phone on invitation as well
					invitation.invitee_phone = phone
					invitation.save()

				send_invitation_notification(request, invitation)
				messages.success(request, f"Invitation sent successfully! Code: {invitation.invitation_code}")
				return redirect('groups:group_detail', group.id)
			else:
				messages.error(request, "Please correct the errors below.")
	else:
		invitation_form = GroupInvitationForm()
		profile_form = BorrowerMiniForm()

	return render(request, 'send_invite.html', {
		'group': group,
		'invitation_form': invitation_form,
		'profile_form': profile_form,
	})



def send_invitation_notification(request, invitation):
	activation_url = request.build_absolute_uri(invitation.get_activation_url())
	sms_body = (
		f"Lumela {invitation.invitee_name or ''}! "
		f"You're invited to join {invitation.group.name}. "
		f"Use code {invitation.invitation_code} or visit {activation_url} to activate."
	)

	try:
		send_sms_smsportal(invitation.invitee_phone, sms_body)
		invitation.sms_sent = True
		invitation.sms_sent_at = timezone.now()
	except Exception as e:
		# Keep going; record failure to messages for the admin view
		messages.warning(request, f"SMS notification failed: {e}")

	if invitation.invitee_email:
		try:
			email_body = (
				f"Hello {invitation.invitee_name or ''},\n\n"
				f"You have been invited to join {invitation.group.name} by {invitation.invited_by.full_name}.\n\n"
				f"{invitation.personal_message or ''}\n\n"
				f"Activate here: {activation_url}\n"
				f"Invitation code: {invitation.invitation_code}\n"
				f"Expires on: {invitation.expires_at.strftime('%d %B %Y')}\n\n"
				f"Thank you,\n{invitation.group.name}"
			)
			send_mail(
				subject=f"Invitation to join {invitation.group.name}",
				message=email_body,
				from_email=settings.EMAIL_HOST_USER,
				recipient_list=[invitation.invitee_email],
				fail_silently=False
			)
			invitation.email_sent = True
			invitation.email_sent_at = timezone.now()
		except Exception as e:
			messages.warning(request, f"Email notification failed: {e}")

	invitation.save(update_fields=['sms_sent', 'sms_sent_at', 'email_sent', 'email_sent_at'])

def search_borrower(request):
	query = request.GET.get('q', '').strip()
	if not query:
		return JsonResponse({'results': []})

	# optionally normalize query for phone searches
	norm_query = normalize_phone(query)

	borrowers = BorrowerProfile.objects.filter(
		Q(phone_number__icontains=norm_query) |
		Q(email_address__icontains=query) |
		Q(full_name__icontains=query)
	)[:10]

	results = []
	for borrower in borrowers:
		results.append({
			'id': borrower.id,
			'full_name': borrower.full_name,
			# keep phone in stored format; optionally format for display
			'phone_number': borrower.phone_number,
			'email': borrower.email_address or (borrower.user.email if borrower.user else ''),
			'has_account': bool(borrower.user),
		})

	return JsonResponse({'results': results})

def normalize_phone2(phone):
	if not phone:
		return ''
	digits = re.sub(r'\D', '', phone)
	# Optionally: handle local-to-international normalization here
	return digits


def normalize_phone(phone):
	
	if not phone:
		return ''
	
	phone = phone.strip().replace(' ', '').replace('-', '')
	
	if phone.startswith('+266'):
		return phone
	elif phone.startswith('266'):
		return '+' + phone
	elif phone.startswith('0'):
		return '+266' + phone[1:]
	else:
		return '+266' + phone


def activate_invite2222(request, code=None):
   
	invitation_code = code or request.POST.get('invitation_code')
	
	if not invitation_code:
		# Show code entry form
		return render(request, 'groups/activate_invite.html', {'show_code_entry': True})
	
	invitation_code = invitation_code.strip().upper()
	
	# ========================================================================
	# STEP 1: Fetch and validate invitation (no locking yet)
	# ========================================================================
	try:
		invitation = GroupInvitation.objects.select_related('group', 'invitee').get(
			invitation_code=invitation_code
		)
	except GroupInvitation.DoesNotExist:
		messages.error(request, "Invalid invitation code. Please check and try again.")
		return render(request, 'groups/activate_invite.html', {'show_code_entry': True})
	
	# Quick status checks before doing heavy work
	if invitation.status != 'pending':
		if invitation.status == 'accepted':
			messages.info(request, "This invitation has already been accepted. Please login.")
		else:
			messages.error(request, f"This invitation is {invitation.get_status_display()}.")
		return redirect('login')
	
	# Check expiry
	if invitation.is_expired():
		invitation.status = 'expired'
		invitation.save(update_fields=['status'])
		messages.error(request, "This invitation has expired. Please contact the group admin.")
		return redirect('login')
	
	# ========================================================================
	# STEP 2: Parse name for user creation
	# ========================================================================
	borrower_profile = invitation.invitee
	
	# Get name from invitation or profile
	name_source = invitation.invitee_name or (borrower_profile.full_name if borrower_profile else '')
	name_parts = name_source.split(maxsplit=1) if name_source else []
	first_name = name_parts[0] if len(name_parts) >= 1 else ''
	last_name = name_parts[1] if len(name_parts) >= 2 else ''
	
	# ========================================================================
	# STEP 3: Handle GET request (show form)
	# ========================================================================
	if request.method != 'POST':
		form = ActivationForm(initial={
			'email': invitation.invitee_email or '',
			'phone_number': invitation.invitee_phone or '',
			'first_name': first_name,
			'last_name': last_name,
		})
		return render(request, 'groups/activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False
		})
	
	# ========================================================================
	# STEP 4: Handle POST request (process activation)
	# ========================================================================
	form = ActivationForm(request.POST)
	
	if not form.is_valid():
		messages.error(request, "Please correct the errors below.")
		return render(request, 'groups/activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False
		})
	
	username = form.cleaned_data['username']
	password = form.cleaned_data['password1']
	email = (invitation.invitee_email or form.cleaned_data.get('email') or '').strip()
	
	# ========================================================================
	# STEP 5: Process activation with proper locking
	# ========================================================================
	try:
		with transaction.atomic():
			# Lock the invitation to prevent concurrent processing
			inv = GroupInvitation.objects.select_for_update().get(pk=invitation.pk)
			
			# Re-check status while locked
			if inv.status != 'pending':
				messages.info(request, "This invitation was processed by another request. Please login.")
				return redirect('login')
			
			if inv.is_expired():
				inv.status = 'expired'
				inv.save(update_fields=['status'])
				messages.error(request, "This invitation expired. Please contact the group admin.")
				return redirect('login')
			
			# ================================================================
			# STEP 5A: Ensure BorrowerProfile exists
			# ================================================================
			if not inv.invitee_id:
				# No profile attached - create one from invitation data
				if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
					messages.error(request, "Invalid invitation - missing contact details. Please contact the group admin.")
					return redirect('login')
				
				borrower_profile = BorrowerProfile.objects.create(
					full_name=(inv.invitee_name or '').strip(),
					phone_number=normalize_phone(inv.invitee_phone) if inv.invitee_phone else '',
					email_address=(inv.invitee_email or '').strip(),
				)
				inv.invitee = borrower_profile
				inv.save(update_fields=['invitee'])
				logger.info("Created BorrowerProfile %s from invitation %s", borrower_profile.pk, inv.pk)
			else:
				# Profile should exist - lock it
				try:
					borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee_id)
				except BorrowerProfile.DoesNotExist:
					# Profile was deleted - recreate from invitation
					if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
						messages.error(request, "Profile not found and invitation has no contact data. Please contact the group admin.")
						return redirect('login')
					
					borrower_profile = BorrowerProfile.objects.create(
						full_name=(inv.invitee_name or '').strip(),
						phone_number=normalize_phone(inv.invitee_phone) if inv.invitee_phone else '',
						email_address=(inv.invitee_email or '').strip(),
					)
					inv.invitee = borrower_profile
					inv.save(update_fields=['invitee'])
					logger.warning("Recreated deleted BorrowerProfile for invitation %s", inv.pk)
			
			# ================================================================
			# STEP 5B: Check if profile already has a user
			# ================================================================
			if borrower_profile.user:
				# Already activated
				if request.user.is_authenticated and request.user.pk == borrower_profile.user.pk:
					# Same user - just add to group if not already member
					membership, created = GroupMembership.objects.get_or_create(
						group=inv.group,
						borrower=borrower_profile,
						defaults={
							'role': 'member',
							'status': 'active',
							'verification_status': 'identity_verified',
							'joined_date': timezone.now()
						}
					)
					inv.mark_accepted()
					
					if created:
						messages.success(request, f"You've been added to {inv.group.name}!")
					else:
						messages.info(request, f"You're already a member of {inv.group.name}.")
					return redirect('borrowers:borrower_index')
				else:
					# Different user or not logged in
					messages.error(request, "This invitation has already been activated. Please login with your existing account.")
					return redirect('login')
			
			# ================================================================
			# STEP 5C: Validate username availability
			# ================================================================
			if User.objects.filter(username__iexact=username).exists():
				form.add_error('username', 'This username is already taken. Please choose another.')
				return render(request, 'groups/activate_invite.html', {
					'form': form,
					'invitation': inv,
					'borrower_profile': borrower_profile,
					'show_code_entry': False
				})
			
			# ================================================================
			# STEP 5D: Create User
			# ================================================================
			try:
				user = User.objects.create_user(
					username=username,
					email=email,
					password=password,
					first_name=first_name,
					last_name=last_name
				)
				logger.info("Created user %s for invitation %s", user.username, inv.pk)
			except IntegrityError as e:
				logger.warning("User creation failed (likely username race): %s", e)
				form.add_error('username', 'This username was just taken. Please choose another.')
				return render(request, 'groups/activate_invite.html', {
					'form': form,
					'invitation': inv,
					'borrower_profile': borrower_profile,
					'show_code_entry': False
				})
			
			# ================================================================
			# STEP 5E: Atomically link user to profile
			# ================================================================
			update_fields = {'user_id': user.pk}
			if hasattr(BorrowerProfile, 'activated_at'):
				update_fields['activated_at'] = timezone.now()
			
			updated = BorrowerProfile.objects.filter(
				pk=borrower_profile.pk,
				user__isnull=True  # Only update if still unclaimed
			).update(**update_fields)
			
			if updated != 1:
				# Profile was claimed by another process concurrently
				logger.warning("BorrowerProfile %s was claimed concurrently during activation", borrower_profile.pk)
				
				# Refresh to see who claimed it
				borrower_profile.refresh_from_db()
				current_user = borrower_profile.user
				
				if current_user:
					# Another process won - check if it's the same person
					if current_user.email and email and current_user.email.lower() == email.lower():
						# Same email - probably same person, delete our temp user and login existing
						logger.info("Email match detected - logging in existing user %s", current_user.username)
						
						try:
							if user.pk != current_user.pk:
								user.delete()
						except Exception as del_err:
							logger.error("Failed to delete temp user: %s", del_err)
						
						# Ensure membership
						GroupMembership.objects.get_or_create(
							group=inv.group,
							borrower=borrower_profile,
							defaults={
								'role': 'member',
								'status': 'active',
								'verification_status': 'identity_verified',
								'joined_date': timezone.now()
							}
						)
						
						try:
							inv.mark_accepted()
						except Exception:
							logger.exception("Failed to mark invitation accepted after concurrent claim")
						
						# Login the existing user
						login(request, current_user)
						messages.success(request, "Your account was activated. Welcome!")
						return redirect('borrowers:borrower_index')
					else:
						# Different email - delete temp user and prompt login
						try:
							user.delete()
						except Exception as del_err:
							logger.error("Failed to delete temp user: %s", del_err)
						
						messages.info(request, "An account already exists for this invitation. Please login or reset your password.")
						return redirect('login')
				
				# Unexpected state - cleanup and show error
				try:
					user.delete()
				except Exception:
					pass
				messages.error(request, "An error occurred during activation. Please contact support.")
				return redirect('login')
			
			# ================================================================
			# STEP 5F: Success - finalize activation
			# ================================================================
			borrower_profile.refresh_from_db()
			
			# Mark invitation accepted
			inv.mark_accepted()
			
			# Create group membership
			GroupMembership.objects.create(
				group=inv.group,
				borrower=borrower_profile,
				role='member',
				status='active',
				verification_status='identity_verified',
				joined_date=timezone.now()
			)
			
			# Log in the user
			login(request, user)
			
			logger.info("Successfully activated invitation %s for user %s", inv.pk, user.username)
			
			messages.success(
				request,
				f"Welcome {borrower_profile.full_name or user.username}! "
				f"Your account has been activated and you are now a member of {inv.group.name}."
			)
			return redirect('borrowers:borrower_index')
	
	except IntegrityError as exc:
		# Fallback for unexpected integrity errors
		error_id = uuid.uuid4().hex[:8]
		logger.exception("IntegrityError during activation (error_id=%s, code=%s): %s", error_id, invitation_code, exc)
		
		# Check if profile got linked despite error
		try:
			current = BorrowerProfile.objects.filter(
				pk=getattr(borrower_profile, 'pk', None),
				user__isnull=False
			).first()
			
			if current and current.user:
				# Profile was linked - ensure membership and mark accepted
				GroupMembership.objects.get_or_create(
					group=invitation.group,
					borrower=current,
					defaults={
						'role': 'member',
						'status': 'active',
						'verification_status': 'identity_verified',
						'joined_date': timezone.now()
					}
				)
				
				try:
					invitation.mark_accepted()
				except Exception:
					logger.exception("Failed to mark invitation accepted in IntegrityError recovery")
				
				messages.success(request, "Your account was activated. Please login.")
				return redirect('login')
		except Exception as recovery_err:
			logger.exception("Error during IntegrityError recovery: %s", recovery_err)
		
		messages.error(
			request,
			f"An error occurred while creating your account (Error ID: {error_id}). "
			f"Please try again or contact support."
		)
		return render(request, 'groups/activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False,
			'error_id': error_id
		})
	
	except Exception as exc:
		# Unexpected errors
		error_id = uuid.uuid4().hex[:8]
		logger.exception("Unexpected activation error (error_id=%s, code=%s): %s", error_id, invitation_code, exc)
		
		# Show error page with support info
		return render(request, 'groups/invite_error.html', {
			'error_id': error_id,
			'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@example.com'),
			'invitation_code': invitation_code
		})



def activate_invite22(request, code=None):
	
	invitation_code = code or request.POST.get('invitation_code')
	if not invitation_code:
		# Show the code entry form
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	invitation_code = invitation_code.strip().upper()

	# Resolve invitation (no locking required yet)
	try:
		invitation = GroupInvitation.objects.get(invitation_code=invitation_code)
	except GroupInvitation.DoesNotExist:
		messages.error(request, "Invalid invitation code. Please check and try again.")
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	# Quick status/expiry checks before heavy work
	if invitation.status != 'pending':
		if invitation.status == 'accepted':
			messages.info(request, "This invitation has already been accepted. Please login.")
			return redirect('login')
		messages.error(request, f"This invitation is {invitation.get_status_display()}.")
		return redirect('login')

	if invitation.is_expired():
		invitation.status = 'expired'
		invitation.save(update_fields=['status'])
		messages.error(request, "This invitation has expired. Please contact the group admin.")
		return redirect('login')

	# BorrowerProfile may be None (invitation.invitee is nullable)
	borrower_profile = invitation.invitee  # may be None

	# Parse name safely for user first/last name
	name_source = (invitation.invitee_name or '') or (borrower_profile.full_name if borrower_profile else '')
	name_parts = name_source.split(maxsplit=1) if name_source else []
	first_name = name_parts[0] if len(name_parts) >= 1 else ''
	last_name = name_parts[1] if len(name_parts) >= 2 else ''

	if request.method == 'POST':
		form = ActivationForm(request.POST)
		if not form.is_valid():
			messages.error(request, "Please correct the errors below.")
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

		username = form.cleaned_data['username']
		password = form.cleaned_data['password1']
		email = (invitation.invitee_email or form.cleaned_data.get('email') or '').strip()

		try:
			with transaction.atomic():
				# Lock the invitation row to serialize acceptance attempts
				inv = GroupInvitation.objects.select_for_update().get(pk=invitation.pk)

				# Re-check status/expiry while locked
				if inv.status != 'pending':
					messages.error(request, "This invitation is no longer available.")
					return redirect('login')
				if inv.is_expired():
					inv.status = 'expired'
					inv.save(update_fields=['status'])
					messages.error(request, "This invitation expired while you were completing the form.")
					return redirect('login')

				# Ensure we have or create a BorrowerProfile to attach the new user to.
				if not inv.invitee_id:
					# Policy decision: create a minimal profile if the invite has contact info.
					if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
						messages.error(request, "Invitation is missing contact details; please contact the group admin.")
						return redirect('login')

					borrower_profile = BorrowerProfile.objects.create(
						full_name=(inv.invitee_name or '').strip(),
						phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
						email_address=(inv.invitee_email or '').strip(),
					)
					# Attach newly created profile to the invitation
					inv.invitee = borrower_profile
					inv.save(update_fields=['invitee'])
				else:
					# Try to lock the existing borrower profile row.
					try:
						borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee_id)
					except BorrowerProfile.DoesNotExist:
						# Profile was deleted after the invite was created. Recreate from invite fields if possible.
						if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
							messages.error(request, "Invitation refers to a missing profile and contains no contact data. Contact the group admin.")
							return redirect('login')
						borrower_profile = BorrowerProfile.objects.create(
							full_name=(inv.invitee_name or '').strip(),
							phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
							email_address=(inv.invitee_email or '').strip(),
						)
						inv.invitee = borrower_profile
						inv.save(update_fields=['invitee'])

				# If borrower_profile already has a user, handle it
				if borrower_profile.user:
					# If the requester is already that user, add them to the group if missing
					if request.user.is_authenticated and request.user.pk == borrower_profile.user.pk:
						if not GroupMembership.objects.filter(group=inv.group, borrower=borrower_profile).exists():
							GroupMembership.objects.create(
								group=inv.group,
								borrower=borrower_profile,
								role='member',
								status='active',
								verification_status='identity_verified',
								joined_date=timezone.now()
							)
						inv.mark_accepted()
						messages.success(request, f"You've been added to {inv.group.name}!")
						return redirect('borrowers:borrower_index')
					# Otherwise, profile already has an account
					messages.error(request, "This profile already has an account. Please login with your existing credentials.")
					return redirect('login')

				# Validate username availability before creating user (case-insensitive)
				if User.objects.filter(username__iexact=username).exists():
					form.add_error('username', 'This username is already taken. Please choose another.')
					return render(request, 'activate_invite.html', {
						'form': form, 'invitation': inv, 'borrower_profile': borrower_profile, 'show_code_entry': False
					})

				# Create the User. This may still raise IntegrityError in very tight races; handle below.
				try:
					user = User.objects.create_user(
						username=username,
						email=email,
						password=password,
						first_name=first_name,
						last_name=last_name
					)
				except IntegrityError as e:
					logger.exception("User creation failed during invite activation: %s", e)
					form.add_error('username', 'This username is already taken. Please choose another.')
					return render(request, 'activate_invite.html', {
						'form': form, 'invitation': inv, 'borrower_profile': borrower_profile, 'show_code_entry': False
					})

				# Atomically claim the borrower_profile for this user only if it is still unclaimed.
				update_kwargs = {'user_id': user.pk}
				# Add activated_at only if the model has the field
				if hasattr(BorrowerProfile, 'activated_at'):
					update_kwargs['activated_at'] = timezone.now()

				updated = BorrowerProfile.objects.filter(pk=borrower_profile.pk, user__isnull=True).update(**update_kwargs)

				if updated != 1:
					# Another process claimed this profile concurrently.
					logger.info("BorrowerProfile %s was claimed concurrently while creating user %s", borrower_profile.pk, user.pk)

					# Refresh the borrower profile and its user to inspect the current state
					current = BorrowerProfile.objects.select_related('user').filter(pk=borrower_profile.pk).first()

					# If we have a current linked user, attempt friendly handling
					if current and current.user:
						try:
							# If emails match, assume same person and sign them in
							if current.user.email and email and current.user.email.lower() == email.lower():
								# Remove the temporary user we created (avoid orphan) if different
								if user.pk and current.user.pk != user.pk:
									try:
										user.delete()
									except Exception:
										logger.exception("Failed to delete temp user %s after concurrent claim", user.pk)

								# Ensure membership exists, mark invite accepted and login the existing user
								if not GroupMembership.objects.filter(group=inv.group, borrower=current).exists():
									GroupMembership.objects.create(
										group=inv.group,
										borrower=current,
										role='member',
										status='active',
										verification_status='identity_verified',
										joined_date=timezone.now()
									)
								try:
									inv.mark_accepted()
								except Exception:
									logger.exception("Failed to mark invitation %s accepted after concurrent claim.", inv.pk)

								login(request, current.user)
								messages.success(request, "Your account was created by another request; we've signed you in and added you to the group.")
								return redirect('borrowers:borrower_index')

							# If email doesn't match, avoid auto-login. Clean up temp user and prompt login/reset.
							try:
								user.delete()
							except Exception:
								logger.exception("Failed to delete temp user %s after concurrent claim", user.pk)

							messages.info(request, "An account already exists for this profile. Please sign in or request a password reset.")
							return redirect('login')

						except Exception:
							logger.exception("Error handling concurrent claim for borrower_profile %s", borrower_profile.pk)
							return redirect('login')

					# Unexpected: no current user found. Cleanup the temp user and show error.
					try:
						user.delete()
					except Exception:
						logger.exception("Failed to delete temp user %s after unexpected concurrent claim", getattr(user, 'pk', None))
					messages.error(request, "An error occurred while processing the invitation. Please contact support.")
					return redirect('login')

				# Success: refresh borrower_profile from DB to get persisted values
				borrower_profile.refresh_from_db()

				# Mark invitation accepted, create membership, log in the user
				inv.mark_accepted()
				GroupMembership.objects.create(
					group=inv.group,
					borrower=borrower_profile,
					role='member',
					status='active',
					verification_status='identity_verified',
					joined_date=timezone.now()
				)

				login(request, user)
				messages.success(request, f"Welcome {borrower_profile.full_name or user.username}! Your account has been activated and you are now a member of {inv.group.name}.")
				return redirect('borrowers:borrower_index')

		except IntegrityError as exc:
			# A fallback catch; we've tried to prevent races, but handle gracefully.
			logger.exception("IntegrityError in activate_invite for code %s: %s", invitation_code, exc)
			# Try to determine whether the borrower_profile got linked by another process
			current = None
			try:
				current = BorrowerProfile.objects.filter(pk=getattr(borrower_profile, 'pk', None), user__isnull=False).first()
			except Exception:
				pass
			if current:
				if not GroupMembership.objects.filter(group=invitation.group, borrower=current).exists():
					GroupMembership.objects.create(
						group=invitation.group,
						borrower=current,
						role='member',
						status='active',
						verification_status='identity_verified',
						joined_date=timezone.now()
					)
				try:
					invitation.mark_accepted()
				except Exception:
					logger.exception("Failed to mark invitation accepted in IntegrityError fallback.")
				messages.success(request, "This invitation was processed by another request. Please login with your account.")
				return redirect('login')

			#messages.error(request, "An error occurred while creating your account. Please try again or contact support.")
			logger.exception("Activation error (id=%s) for invite %s: %s", error_id, invitation_code, exc)
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

		except Exception as exc:
			# Unexpected errors: log full stacktrace with reference id and show friendly error page.
			error_id = uuid.uuid4().hex[:8]
			logger.exception("Activation error (id=%s) for invite %s: %s", error_id, invitation_code, exc)
			print(f"[ACTIVATE_INVITE ERROR id={error_id}]", flush=True)
			return render(request, 'invite_error.html', {
				'error_id': error_id,
				'support_email': getattr(settings, 'SUPPORT_EMAIL', None),
			})

	else:
		# GET: present the activation form pre-filled with available data
		form = ActivationForm(initial={
			'email': invitation.invitee_email or '',
			'phone_number': invitation.invitee_phone or '',
			'first_name': first_name,
			'last_name': last_name,
		})
		return render(request, 'activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False
		})

def activate_invite3(request, code=None):
	
	invitation_code = code or request.POST.get('invitation_code')
	if not invitation_code:
		# Show the code entry form
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	invitation_code = invitation_code.strip().upper()

	# Resolve invitation (no locking required yet)
	try:
		invitation = GroupInvitation.objects.get(invitation_code=invitation_code)
	except GroupInvitation.DoesNotExist:
		messages.error(request, "Invalid invitation code. Please check and try again.")
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	# Quick status/expiry checks before heavy work
	if invitation.status != 'pending':
		if invitation.status == 'accepted':
			messages.info(request, "This invitation has already been accepted. Please login.")
			return redirect('login')
		messages.error(request, f"This invitation is {invitation.get_status_display()}.")
		return redirect('login')

	if invitation.is_expired():
		invitation.status = 'expired'
		invitation.save(update_fields=['status'])
		messages.error(request, "This invitation has expired. Please contact the group admin.")
		return redirect('login')

	# BorrowerProfile may be None (invitation.invitee is nullable)
	borrower_profile = invitation.invitee  # may be None

	# Parse name safely for user first/last name
	name_source = (invitation.invitee_name or '') or (borrower_profile.full_name if borrower_profile else '')
	name_parts = name_source.split(maxsplit=1) if name_source else []
	first_name = name_parts[0] if len(name_parts) >= 1 else ''
	last_name = name_parts[1] if len(name_parts) >= 2 else ''

	if request.method == 'POST':
		form = ActivationForm(request.POST)
		if not form.is_valid():
			messages.error(request, "Please correct the errors below.")
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

		username = form.cleaned_data['username']
		password = form.cleaned_data['password1']
		email = (invitation.invitee_email or form.cleaned_data.get('email') or '').strip()

		try:
			with transaction.atomic():
				# Lock the invitation row to serialize acceptance attempts
				inv = GroupInvitation.objects.select_for_update().get(pk=invitation.pk)

				# Re-check status/expiry while locked
				if inv.status != 'pending':
					messages.error(request, "This invitation is no longer available.")
					return redirect('login')
				if inv.is_expired():
					inv.status = 'expired'
					inv.save(update_fields=['status'])
					messages.error(request, "This invitation expired while you were completing the form.")
					return redirect('login')

				# Ensure we have or create a BorrowerProfile to attach the new user to.
				if not inv.invitee_id:
					# Policy decision: create a minimal profile if the invite has contact info.
					if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
						messages.error(request, "Invitation is missing contact details; please contact the group admin.")
						return redirect('login')

					borrower_profile = BorrowerProfile.objects.create(
						full_name=(inv.invitee_name or '').strip(),
						phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
						email_address=(inv.invitee_email or '').strip(),
					)
					# Attach newly created profile to the invitation
					inv.invitee = borrower_profile
					inv.save(update_fields=['invitee'])
				else:
					# Try to lock the existing borrower profile row.
					try:
						borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee_id)
					except BorrowerProfile.DoesNotExist:
						# Profile was deleted after the invite was created. Recreate from invite fields if possible.
						if not (inv.invitee_name or inv.invitee_phone or inv.invitee_email):
							messages.error(request, "Invitation refers to a missing profile and contains no contact data. Contact the group admin.")
							return redirect('login')
						borrower_profile = BorrowerProfile.objects.create(
							full_name=(inv.invitee_name or '').strip(),
							phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
							email_address=(inv.invitee_email or '').strip(),
						)
						inv.invitee = borrower_profile
						inv.save(update_fields=['invitee'])

				# If borrower_profile already has a user, handle it
				if borrower_profile.user:
					# If the requester is already that user, add them to the group if missing
					if request.user.is_authenticated and request.user.pk == borrower_profile.user.pk:
						if not GroupMembership.objects.filter(group=inv.group, borrower=borrower_profile).exists():
							GroupMembership.objects.create(
								group=inv.group,
								borrower=borrower_profile,
								role='member',
								status='active',
								verification_status='identity_verified',
								joined_date=timezone.now()
							)
						inv.mark_accepted()
						messages.success(request, f"You've been added to {inv.group.name}!")
						return redirect('borrowers:borrower_index')
					# Otherwise, profile already has an account
					messages.error(request, "This profile already has an account. Please login with your existing credentials.")
					return redirect('login')

				# Validate username availability before creating user (case-insensitive)
				if User.objects.filter(username__iexact=username).exists():
					form.add_error('username', 'This username is already taken. Please choose another.')
					return render(request, 'activate_invite.html', {
						'form': form, 'invitation': inv, 'borrower_profile': borrower_profile, 'show_code_entry': False
					})

				# Create the User. This may still raise IntegrityError in very tight races; handle below.
				try:
					user = User.objects.create_user(
						username=username,
						email=email,
						password=password,
						first_name=first_name,
						last_name=last_name
					)
				except IntegrityError as e:
					logger.exception("User creation failed during invite activation: %s", e)
					form.add_error('username', 'This username is already taken. Please choose another.')
					return render(request, 'activate_invite.html', {
						'form': form, 'invitation': inv, 'borrower_profile': borrower_profile, 'show_code_entry': False
					})

				# Atomically claim the borrower_profile for this user only if it is still unclaimed.
				updated = BorrowerProfile.objects.filter(pk=borrower_profile.pk, user__isnull=True).update(
					user_id=user.pk,
					#activated_at=timezone.now() if hasattr(borrower_profile, 'activated_at') else None
				)

				
				if updated != 1:
				
					# updated != 1 branch (improved handling)
					logger.info("BorrowerProfile %s was claimed concurrently while creating user %s", borrower_profile.pk, user.pk)

					# Refresh the borrower profile from DB and get the current linked user
					current = BorrowerProfile.objects.select_related('user').filter(pk=borrower_profile.pk).first()
					if current and current.user:
						# If the current user looks like the same person (email match), log them in:
						try:
							if current.user.email and email and current.user.email.lower() == email.lower():
								# Clean up the temporary user we created (avoid orphan) if it's different
								if user.pk and current.user.pk != user.pk:
									try:
										user.delete()
									except Exception:
										logger.exception("Failed to delete temp user %s after concurrent claim", user.pk)
								# Log the existing account in for the visitor
								login(request, current.user)
								# Ensure membership exists
								if not GroupMembership.objects.filter(group=inv.group, borrower=current).exists():
									GroupMembership.objects.create(
										group=inv.group,
										borrower=current,
										role='member',
										status='active',
										verification_status='identity_verified',
										joined_date=timezone.now()
									)
								inv.mark_accepted()
								messages.success(request, "Your account was created by another request; we've signed you in and added you to the group.")
								return redirect('borrowers:borrower_index')

							# If email doesn't match, avoid auto-login. Remove temp user and show helpful next step:
							try:
								user.delete()
							except Exception:
								logger.exception("Failed to delete temp user %s after concurrent claim", user.pk)

							# Show a helpful page so the person can get back into their account:
							# You can render a template that offers "Send login link" / "Reset password" options.
							messages.info(request, "An account already exists for this profile. Please sign in or request a password reset.")
							return redirect('login')

						except Exception:
							logger.exception("Error handling concurrent claim for borrower_profile %s", borrower_profile.pk)
							# fallback: redirect to login
							return redirect('login')
					else:
						# No current user found — unexpected: keep the previous cleanup behavior
						try:
							user.delete()
						except Exception:
							logger.exception("Failed to delete temp user %s after unexpected concurrent claim", getattr(user, 'pk', None))
						messages.error(request, "An error occurred while processing the invitation. Please contact support.")
						return redirect('login')

				# Success: refresh borrower_profile from DB to get persisted values
				borrower_profile.refresh_from_db()

				# Mark invitation accepted, create membership, log in the user
				inv.mark_accepted()
				GroupMembership.objects.create(
					group=inv.group,
					borrower=borrower_profile,
					role='member',
					status='active',
					verification_status='identity_verified',
					joined_date=timezone.now()
				)

				login(request, user)
				messages.success(request, f"Welcome {borrower_profile.full_name or user.username}! Your account has been activated and you are now a member of {inv.group.name}.")
				return redirect('borrowers:borrower_index')

		except IntegrityError as exc:
			# A fallback catch; we've tried to prevent races, but handle gracefully.
			logger.exception("IntegrityError in activate_invite for code %s: %s", invitation_code, exc)
			# Try to determine whether the borrower_profile got linked by another process
			current = None
			try:
				current = BorrowerProfile.objects.filter(pk=getattr(borrower_profile, 'pk', None), user__isnull=False).first()
			except Exception:
				pass
			if current:
				if not GroupMembership.objects.filter(group=invitation.group, borrower=current).exists():
					GroupMembership.objects.create(
						group=invitation.group,
						borrower=current,
						role='member',
						status='active',
						verification_status='identity_verified',
						joined_date=timezone.now()
					)
				try:
					invitation.mark_accepted()
				except Exception:
					logger.exception("Failed to mark invitation accepted in IntegrityError fallback.")
				messages.success(request, "This invitation was processed by another request. Please login with your account.")
				return redirect('login')

			messages.error(request, "An error occurred while creating your account. Please try again or contact support.")
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

	else:
		# GET: present the activation form pre-filled with available data
		form = ActivationForm(initial={
			'email': invitation.invitee_email or '',
			'phone_number': invitation.invitee_phone or '',
			'first_name': first_name,
			'last_name': last_name,
		})
		return render(request, 'activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False
		})


def activate_invite(request, code=None):

	invitation_code = code or request.POST.get('invitation_code')
	if not invitation_code:
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	invitation_code = invitation_code.strip().upper()

	# find invitation (no locks needed for initial GET)
	try:
		invitation = GroupInvitation.objects.get(invitation_code=invitation_code)
	except GroupInvitation.DoesNotExist:
		messages.error(request, "Invalid invitation code. Please check and try again.")
		return render(request, 'activate_invite.html', {'show_code_entry': True})

	# handle obvious non-pending states and expiry
	if invitation.status != 'pending':
		if invitation.status == 'accepted':
			messages.info(request, "This invitation has already been accepted. Please login.")
			return redirect('login')
		messages.error(request, f"This invitation is {invitation.get_status_display()}.")
		return redirect('login')

	if invitation.is_expired():
		invitation.status = 'expired'
		invitation.save(update_fields=['status'])
		messages.error(request, "This invitation has expired. Please contact the group admin.")
		return redirect('login')

	borrower_profile = invitation.invitee
	if not borrower_profile:
		messages.error(request, "Invalid invitation - no profile found. Please contact the group admin.")
		return redirect('login')

	# safe name parsing
	name_source = invitation.invitee_name or borrower_profile.full_name or ""
	name_parts = name_source.split(maxsplit=1)
	first_name = name_parts[0] if name_parts else ""
	last_name = name_parts[1] if len(name_parts) > 1 else ""

	if request.method == 'POST':
		form = ActivationForm(request.POST)
		if not form.is_valid():
			messages.error(request, "Please correct the errors below.")
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

		username = form.cleaned_data['username']
		password = form.cleaned_data['password1']
		email = invitation.invitee_email or form.cleaned_data.get('email', '') or ''

		# Begin atomic block and lock the invitation row (and borrower) to prevent races
		try:
			with transaction.atomic():
				# lock the invitation row so only one transaction can proceed past here
				inv = GroupInvitation.objects.select_for_update().get(pk=invitation.pk)

				# re-check status and expiry while locked
				if inv.status != 'pending':
					messages.error(request, "This invitation is no longer available.")
					return redirect('login')
				if inv.is_expired():
					inv.status = 'expired'
					inv.save(update_fields=['status'])
					messages.error(request, "This invitation expired while you were completing the form.")
					return redirect('login')

				# re-lock the borrower profile row (if present) to avoid concurrent profile changes
				#borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee.pk)
				#borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee_id)

				# If no invitee attached (invitee_id is NULL) -> create one from invite fields (or abort)
				if not inv.invitee_id:
					# If you prefer to abort instead of creating, set create_missing_profile = False
					create_missing_profile = True

					if not create_missing_profile:
						messages.error(request, "This invitation is invalid (no profile attached). Please contact the group admin.")
						return redirect('login')

					# Ensure we have at least phone or name to create a minimal profile
					if not (inv.invitee_phone or inv.invitee_name or inv.invitee_email):
						messages.error(request, "Invitation is missing contact details; contact the group admin.")
						return redirect('login')

					borrower_profile = BorrowerProfile.objects.create(
						full_name=(inv.invitee_name or '').strip(),
						phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
						email_address=(inv.invitee_email or '').strip(),
					)
					# attach the newly created profile to the invitation
					inv.invitee = borrower_profile
					inv.save(update_fields=['invitee'])

				else:
					# invitee_id exists — try to lock the borrower profile row
					try:
						borrower_profile = BorrowerProfile.objects.select_for_update().get(pk=inv.invitee_id)
					except BorrowerProfile.DoesNotExist:
						# The profile was deleted after the invite was created. Decide policy:
						# - recreate a profile from invite fields (below), or
						# - abort with an error to the user.
						# We'll recreate using the invite contact fields.
						if not (inv.invitee_phone or inv.invitee_name or inv.invitee_email):
							messages.error(request, "Invitation refers to a missing profile and contains no contact data. Contact the group admin.")
							return redirect('login')

						borrower_profile = BorrowerProfile.objects.create(
							full_name=(inv.invitee_name or '').strip(),
							phone_number=(normalize_phone(inv.invitee_phone) if inv.invitee_phone else ''),
							email_address=(inv.invitee_email or '').strip(),
						)
						inv.invitee = borrower_profile
						inv.save(update_fields=['invitee'])

				# If profile already linked, handle it
				if borrower_profile.user:
					# if same authenticated user, add membership; otherwise tell user to login
					if request.user.is_authenticated and request.user.pk == borrower_profile.user.pk:
						if not GroupMembership.objects.filter(group=inv.group, borrower=borrower_profile).exists():
							GroupMembership.objects.create(
								group=inv.group,
								borrower=borrower_profile,
								role='member',
								status='active',
								verification_status='identity_verified',
								joined_date=timezone.now()
							)
						inv.mark_accepted()
						messages.success(request, f"You've been added to {inv.group.name}!")
						return redirect('borrowers:borrower_index')
					messages.error(request, "This profile already has an account. Please login with your existing credentials.")
					return redirect('login')

				# Ensure username not already taken (case-insensitive)
				if User.objects.filter(username__iexact=username).exists():
					form.add_error('username', 'This username is already taken. Please choose another.')
					return render(request, 'activate_invite.html', {
						'form': form, 'invitation': inv, 'borrower_profile': borrower_profile, 'show_code_entry': False
					})

				# Create user and link to profile
				user = User.objects.create_user(
					username=username,
					email=email,
					password=password,
					first_name=first_name,
					last_name=last_name
				)

				# assign and save borrower profile (we have the borrower row locked)
				borrower_profile.user = user
				borrower_profile.activated_at = timezone.now() if hasattr(borrower_profile, 'activated_at') else None
				borrower_profile.save()

				# mark invitation accepted
				inv.mark_accepted()

				# create membership
				GroupMembership.objects.create(
					group=inv.group,
					borrower=borrower_profile,
					role='member',
					status='active',
					verification_status='identity_verified',
					joined_date=timezone.now()
				)

				# login and redirect
				login(request, user)
				messages.success(request, f"Welcome {borrower_profile.full_name}! Your account has been activated and you are now a member of {inv.group.name}.")
				return redirect('borrowers:borrower_index')

		except IntegrityError as exc:
			# Possible outcomes:
			# - A concurrent transaction linked a user to this profile or to another profile.
			# - A user with same username existed and race caused odd state.
			# Handle gracefully: reload state and redirect appropriately.
			# Do not attempt to continue within the same atomic block after IntegrityError.
			# Log exc in real app.
			# Try to determine whether the borrower_profile was linked by another transaction:
			existing_profile = BorrowerProfile.objects.filter(user__isnull=False, pk=borrower_profile.pk).first()
			if existing_profile:
				# Someone else already linked the profile -> accept invitation and add membership if missing
				if not GroupMembership.objects.filter(group=invitation.group, borrower=existing_profile).exists():
					GroupMembership.objects.create(
						group=invitation.group,
						borrower=existing_profile,
						role='member',
						status='active',
						verification_status='identity_verified',
						joined_date=timezone.now()
					)
				try:
					# mark invitation accepted (safe in a new transaction)
					invitation.mark_accepted()
				except Exception:
					pass
				messages.success(request, "This profile was activated by another process. Please login with your account.")
				return redirect('login')

			# Otherwise, fallback to generic error
			messages.error(request, "An error occurred while creating your account. Please try again or contact support.")
			return render(request, 'activate_invite.html', {
				'form': form, 'invitation': invitation, 'borrower_profile': borrower_profile, 'show_code_entry': False
			})

	else:
		# GET: render form prefilled
		form = ActivationForm(initial={
			'email': invitation.invitee_email or '',
			'phone_number': invitation.invitee_phone,
			'first_name': first_name,
			'last_name': last_name,
		})
		return render(request, 'activate_invite.html', {
			'form': form,
			'invitation': invitation,
			'borrower_profile': borrower_profile,
			'show_code_entry': False
		})




def admin_create_invite(request):

	# Permission check: require the user to have a BorrowerProfile and be a group admin or staff.
	borrower_profile = getattr(request.user, 'borrower', None)
	if not borrower_profile or not (borrower_profile.is_group_admin or request.user.is_staff):
		return HttpResponseForbidden("You do not have permission to invite members to groups.")

	if request.method == "POST":
		form = AdminCreateInviteForm(request.POST)
		if form.is_valid():
			with transaction.atomic():
				# Let the form build the invitation instance, but do not commit so we can set invited_by
				invitation = form.save(commit=False)
				invitation.invited_by = borrower_profile

				# Ensure we set a sensible sent_at if not set by the form
				if not getattr(invitation, 'sent_at', None):
					invitation.sent_at = timezone.now()

				invitation.save()
				form.save_m2m()

				# Build absolute activation URL
				activation_path = invitation.get_activation_url()
				activation_url = request.build_absolute_uri(activation_path)

				# Example: send email if invitee_email present and you want to send
				if invitation.invitee_email:
					try:
						send_invite_email(invitation, activation_url)
						invitation.email_sent = True
						invitation.email_sent_at = timezone.now()
					except Exception:
						# Log exception in real code. Keep invitation.email_sent False.
						pass

				# Example: send SMS if phone present (replace with your SMS gateway)
				if invitation.invitee_phone:
					try:
						send_invite_sms(invitation, activation_url)
						invitation.sms_sent = True
						invitation.sms_sent_at = timezone.now()
					except Exception:
						# Log exception in real code.
						pass

				# Persist any updated flags
				invitation.save(update_fields=[
					'email_sent', 'email_sent_at', 'sms_sent', 'sms_sent_at'
				])

			messages.success(request, "Invitation created and dispatched (where contact provided).")
			# Redirect to the group's detail view (adjust name/args to your URLconf)
			return redirect(reverse('groups:detail', args=[invitation.group.pk]))
	else:
		form = AdminCreateInviteForm()

	return render(request, "admin_create_invite.html", {
		"form": form,
		"inviter": borrower_profile,
	})


# --- Helper send functions (replace with your actual email/SMS logic or async tasks) ---
def send_invite_email(invitation: GroupInvitation, activation_url: str):

	subject = f"You've been invited to join {invitation.group.name}"
	body = (
		f"Hello {invitation.invitee_name or ''},\n\n"
		f"{invitation.invited_by} has invited you to join the group \"{invitation.group.name}\".\n\n"
		f"Message from inviter:\n{invitation.personal_message}\n\n"
		f"Activate your invitation here:\n{activation_url}\n\n"
		"If you did not expect this, you can ignore this message.\n"
	)
	# NOTE: settings.EMAIL_FROM must be configured in your Django settings
	send_mail(subject, body, None, [invitation.invitee_email], fail_silently=False)


def send_invite_sms(invitation: GroupInvitation, activation_url: str):
  
	sms_body = f"Invite to {invitation.group.name}: {activation_url}"
	# Example: send via your SMS gateway client here, or enqueue a Celery task.
	# raise NotImplementedError("Hook up your SMS provider here.")
	# For now we just return the prepared message so tests/dev can inspect it.
	return sms_body

def activate_invite(request, code):

	# fetch with select_for_update to avoid races
	invitation = get_object_or_404(GroupInvitation, invitation_code=code)

	# if expired or withdrawn decline flow
	if invitation.is_expired():
		messages.error(request, "This invitation has expired.")
		invitation.status = 'expired'
		invitation.save(update_fields=['status'])
		return render(request, "invite_expired.html", {"invitation": invitation})

	if invitation.status not in ('pending',):
		# Already acted upon
		messages.info(request, f"This invitation is {invitation.status}.")
		return render(request, "groups/invite_status.html", {"invitation": invitation})

	# If there's an invitee profile and already linked to a user
	if invitation.invitee and invitation.invitee.user:
		messages.info(request, "This invitation is already accepted. Please sign in.")
		return redirect('account_login')  # change to your login url name

	if request.method == "POST":
		form = InviteAcceptanceForm(request.POST)
		if form.is_valid():
			with transaction.atomic():
				# Lock the invitation row
				inv = GroupInvitation.objects.select_for_update().get(pk=invitation.pk)

				if inv.is_expired():
					messages.error(request, "Sorry, invitation expired while you were completing the form.")
					inv.status = 'expired'
					inv.save(update_fields=['status'])
					return render(request, "groups/invite_expired.html", {"invitation": inv})

				if inv.status != 'pending':
					messages.error(request, "This invitation is no longer available.")
					return render(request, "groups/invite_status.html", {"invitation": inv})

				username = form.cleaned_data['username']
				password = form.cleaned_data['password1']
				email = form.cleaned_data.get('email') or inv.invitee_email or ''

				user = User.objects.create_user(username=username, email=email, password=password)
				# link to existing invitee profile or create one from invitation fields
				profile = inv.invitee
				if profile is None:
					profile = BorrowerProfile.objects.create(
						user=user,
						full_name=inv.invitee_name or "",
						phone_number=inv.invitee_phone or "",
						email_address=inv.invitee_email or email or "",
					)
				else:
					# if profile exists but has no user set
					profile.user = user
					# fill missing contact fields if empty
					if not profile.phone_number and inv.invitee_phone:
						profile.phone_number = inv.invitee_phone
					if not profile.email_address and (inv.invitee_email or email):
						profile.email_address = inv.invitee_email or email
					profile.save()

				# Link profile.user to the created user (ensure it's saved)
				if not profile.user_id:
					profile.user = user
					profile.save()

				# Mark invitation accepted and save responded_at
				inv.mark_accepted()

				# Optionally record that email was confirmed etc. (depends on your flow)
				# Login user and redirect to group page
				login(request, user)
				messages.success(request, "Welcome — your account has been created and linked to the group.")
				return redirect(reverse('groups:detail', args=[inv.group.pk]))
	else:
		form = InviteAcceptanceForm(initial={"email": invitation.invitee_email})

	return render(request, "groups/accept_invitation.html", {
		"form": form,
		"invitation": invitation,
	})




@login_required
def send_group_invite(request, group_id):
	
	group = get_object_or_404(BorrowerGroup, id=group_id)
	inviter = request.user.borrower
	
	# Check if user is admin of this group
	if group.admin != inviter and inviter not in group.sub_admins.all():
		messages.error(request, "Only group admins can send invitations.")
		return redirect('groups:group_detail', group.id)
	
	if request.method == 'POST':
		invitation_form = GroupInvitationForm(request.POST)
		profile_form = BorrowerMiniForm(request.POST)
		
		invite_type = request.POST.get('invite_type', 'new')
		
		if invite_type == 'existing':
			# Inviting existing user - skip profile creation
			if invitation_form.is_valid():
				phone = invitation_form.cleaned_data['invitee_phone']
				
				# Find existing borrower by phone
				existing_borrower = BorrowerProfile.objects.filter(phone_number=phone).first()
				
				if not existing_borrower:
					messages.error(request, f"No user found with phone number {phone}.")
					return render(request, 'send_invite.html', {
						'group': group,
						'invitation_form': invitation_form,
						'profile_form': profile_form,
					})
				
				# Check if already a member
				if GroupMembership.objects.filter(group=group, borrower=existing_borrower).exists():
					messages.warning(request, f"{existing_borrower.full_name} is already a member of this group.")
					return redirect('groups:group_detail', group.id)
				
				# Check if already invited
				if GroupInvitation.objects.filter(
					group=group,
					invitee=existing_borrower,
					status='pending'
				).exists():
					messages.warning(request, f"{existing_borrower.full_name} already has a pending invitation.")
					return redirect('groups:group_detail', group.id)
				
				# Create invitation
				with transaction.atomic():
					invitation = invitation_form.save(commit=False)
					invitation.group = group
					invitation.invited_by = inviter
					invitation.invitee = existing_borrower
					invitation.invitee_name = existing_borrower.full_name
					invitation.invitee_phone = existing_borrower.phone_number
					invitation.invitee_email = existing_borrower.email_address or existing_borrower.user.email if existing_borrower.user else None
					invitation.save()
					
					# Send notification
					send_invitation_notification(request, invitation)
					
					messages.success(request, f"Invitation sent to {existing_borrower.full_name}!")
					return redirect('groups:group_detail', group.id)
		
		else:  # invite_type == 'new'
			# Creating new borrower profile
			if invitation_form.is_valid() and profile_form.is_valid():
				phone = invitation_form.cleaned_data['invitee_phone']
				
				# Check if borrower with this phone already exists
				existing_borrower = BorrowerProfile.objects.filter(phone_number=phone).first()
				
				if existing_borrower:
					if existing_borrower.user:
						messages.error(
							request,
							f"A user with phone {phone} already exists and has an active account. "
							f"Please use 'Existing User' option instead."
						)
						return render(request, 'invite_borrower.html', {
							'group': group,
							'invitation_form': invitation_form,
							'profile_form': profile_form,
						})
					else:
						# Profile exists but no user account - can reuse
						borrower_profile = existing_borrower
						# Update profile with any new information
						for field in profile_form.cleaned_data:
							setattr(borrower_profile, field, profile_form.cleaned_data[field])
						borrower_profile.save()
				else:
					# Create new borrower profile
					with transaction.atomic():
						borrower_profile = profile_form.save(commit=False)
						borrower_profile.created_by_admin = inviter
						borrower_profile.save()
				
				# Create invitation
				with transaction.atomic():
					invitation = invitation_form.save(commit=False)
					invitation.group = group
					invitation.invited_by = inviter
					invitation.invitee = borrower_profile
					invitation.save()
					
					# Send notification
					send_invitation_notification(request, invitation)
					
					messages.success(
						request,
						f"Invitation sent successfully! Code: {invitation.invitation_code}"
					)
					return redirect('groups:group_detail', group.id)
			else:
				# Form errors
				messages.error(request, "Please correct the errors below.")
	
	else:
		invitation_form = GroupInvitationForm()
		profile_form = BorrowerMiniForm()
	
	return render(request, 'send_invite.html', {
		'group': group,
		'invitation_form': invitation_form,
		'profile_form': profile_form,
	})


def send_invitation_notification(request, invitation):
	
	activation_url = request.build_absolute_uri(invitation.get_activation_url())
	
	# Prepare message
	sms_body = (
		f"Lumela {invitation.invitee_name}! "
		f"You've been invited to join {invitation.group.name}. "
		f"Use code {invitation.invitation_code} or visit {activation_url} to activate your account."
	)
	
	# Send SMS
	try:
		send_sms_smsportal(invitation.invitee_phone, sms_body)
		invitation.sms_sent = True
		invitation.sms_sent_at = timezone.now()
	except Exception as e:
		messages.warning(request, f"SMS notification failed: {str(e)}")
	
	# Send Email (if email provided)
	if invitation.invitee_email:
		try:
			email_body = f
			#Lumela {invitation.invitee_name},
			
			#You have been invited to join {invitation.group.name} by {invitation.invited_by.full_name}.
			
			#{invitation.personal_message if invitation.personal_message else ''}
			
			#To activate your account, please visit:
			#{activation_url}
			
			#Or use invitation code: {invitation.invitation_code}
			
			#This invitation expires on: {invitation.expires_at.strftime('%d %B %Y')}
			
			#Thank you,
			#{invitation.group.name}
			
			
			send_mail(
				subject=f"Invitation to join {invitation.group.name}",
				message=email_body,
				from_email=settings.EMAIL_HOST_USER,
				recipient_list=[invitation.invitee_email],
				fail_silently=False
			)
			invitation.email_sent = True
			invitation.email_sent_at = timezone.now()
		except Exception as e:
			messages.warning(request, f"Email notification failed: {str(e)}")
	
	invitation.save()


@login_required
def search_borrower(request):
	
	query = request.GET.get('q', '').strip()
	
	if not query:
		return JsonResponse({'results': []})
	
	# Search by phone or email
	borrowers = BorrowerProfile.objects.filter(
		django_models.Q(phone_number__icontains=query) |
		django_models.Q(email_address__icontains=query) |
		django_models.Q(full_name__icontains=query)
	)[:10]  # Limit to 10 results
	
	results = []
	for borrower in borrowers:
		results.append({
			'id': borrower.id,
			'full_name': borrower.full_name,
			'phone_number': borrower.phone_number,
			'email': borrower.email_address or (borrower.user.email if borrower.user else ''),
			'has_account': bool(borrower.user),
		})
	
	return JsonResponse({'results': results})



def activate_invite(request, code=None):
	
	# Get invitation code
	invitation_code = code or request.POST.get('invitation_code')
	
	if not invitation_code:
		return render(request, 'activate_invite.html', {
			'show_code_entry': True
		})
	
	invitation_code = invitation_code.strip().upper()
	
	# Get invitation
	try:
		invitation = GroupInvitation.objects.get(invitation_code=invitation_code)
	except GroupInvitation.DoesNotExist:
		messages.error(request, "Invalid invitation code. Please check and try again.")
		return render(request, 'activate_invite.html', {
			'show_code_entry': True
		})
	
	# Check if already used
	if invitation.status != 'pending':
		if invitation.status == 'accepted':
			messages.info(request, "This invitation has already been accepted. Please login.")
			return redirect('login')
		else:
			messages.error(request, f"This invitation is {invitation.get_status_display()}.")
			return redirect('login')
	
	# Check if expired
	if invitation.is_expired():
		invitation.status = 'expired'
		invitation.save()
		messages.error(request, "This invitation has expired. Please contact the group admin.")
		return redirect('login')
	
	borrower_profile = invitation.invitee
	
	if not borrower_profile:
		messages.error(request, "Invalid invitation - no profile found. Please contact the group admin.")
		return redirect('login')
	
	# ✅ FIX: Check if profile already has a user
	if borrower_profile.user:
		# Profile already activated - check if it's the current user
		if request.user.is_authenticated and request.user == borrower_profile.user:
			# Same user trying to activate again - just add them to the group
			if not GroupMembership.objects.filter(group=invitation.group, borrower=borrower_profile).exists():
				GroupMembership.objects.create(
					group=invitation.group,
					borrower=borrower_profile,
					role='member',
					status='active',
					verification_status='identity_verified',
					joined_date=timezone.now()
				)
				invitation.mark_accepted()
				messages.success(request, f"You've been added to {invitation.group.name}!")
			else:
				messages.info(request, f"You're already a member of {invitation.group.name}.")
			return redirect('borrowers:borrower_index')
		else:
			messages.error(request, "This profile already has an account. Please login with your existing credentials.")
			return redirect('login')
	
	# Parse name for user creation
	name_parts = invitation.invitee_name.split(maxsplit=1)
	first_name = name_parts[0]
	last_name = name_parts[1] if len(name_parts) > 1 else ""
	
	if request.method == 'POST':
		form = ActivationForm(request.POST)
		
		if form.is_valid():
			username = form.cleaned_data['username']
			password = form.cleaned_data['password1']
			email = invitation.invitee_email or ''
			
			try:
				with transaction.atomic():
					# ✅ Check again if user already exists (race condition protection)
					if borrower_profile.user:
						messages.error(request, "This profile has already been activated. Please login.")
						return redirect('login')
					
					# Create user account
					user = User.objects.create_user(
						username=username,
						email=email,
						password=password,
						first_name=first_name,
						last_name=last_name
					)
					
					# Link user to borrower profile
					borrower_profile.user = user
					borrower_profile.activated_at = timezone.now()
					borrower_profile.save()
					
					# Mark invitation as accepted
					invitation.mark_accepted()
					
					# Create group membership
					GroupMembership.objects.create(
						group=invitation.group,
						borrower=borrower_profile,
						role='member',
						status='active',
						verification_status='identity_verified',
						joined_date=timezone.now()
					)
					
					# Login the new user
					login(request, user)
					
					messages.success(
						request,
						f"Welcome {borrower_profile.full_name}! Your account has been activated. "
						f"You are now a member of {invitation.group.name}."
					)
					return redirect('borrowers:borrower_index')
					
			except IntegrityError as e:
				# Handle any database integrity issues
				if 'username' in str(e).lower():
					form.add_error('username', 'This username is already taken. Please choose another.')
				elif 'user_id' in str(e).lower():
					messages.error(request, "This profile has already been activated. Please login with your existing account.")
					return redirect('login')
				else:
					messages.error(request, "An error occurred during activation. Please try again or contact support.")
			except Exception as e:
				messages.error(request, f"An unexpected error occurred: {str(e)}")
		else:
			# Form validation errors
			messages.error(request, "Please correct the errors below.")
	
	else:
		# Pre-fill form with invitation data
		form = ActivationForm(initial={
			'email': invitation.invitee_email or '',
			'phone_number': invitation.invitee_phone,
			'first_name': first_name,
			'last_name': last_name,
		})
	
	return render(request, 'activate_invite.html', {
		'form': form,
		'invitation': invitation,
		'borrower_profile': borrower_profile,
		'show_code_entry': False,
	})
"""	



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


@login_required
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

@login_required
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


@login_required
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
						
						send_mail(
							subject=f"Invitation Withdrawn - {invitation.group.name}",
							message=email_body,
							from_email=settings.EMAIL_HOST_USER,
							recipient_list=[invitation.invitee_email],
							fail_silently=True
						)
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


@login_required
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
					
					send_mail(
						subject=f"Reminder: Invitation to join {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[invitation.invitee_email],
						fail_silently=False
					)
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


@login_required
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
					
					send_mail(
						subject=f"Invitation Extended - {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[invitation.invitee_email],
						fail_silently=True
					)
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
					
					send_mail(
						subject=f"Invitation Declined - {invitation.group.name}",
						message=email_body,
						from_email=settings.EMAIL_HOST_USER,
						recipient_list=[email],
						fail_silently=True
					)
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


@login_required
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
@login_required
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

