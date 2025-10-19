from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from datetime import date
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
from django.core.mail import send_mail
from django.conf import settings

from .models import (
	BorrowerGroup, GroupMembership, GroupInvitation,
	GroupJoinRequest, GroupConstitution, GroupTypeSpecificSettings
)
from borrowers.models import BorrowerProfile
from .forms import (
	BorrowerGroupForm, GroupConstitutionForm, ActivationForm,
	GroupTypeSpecificSettingsForm, GroupJoinRequestForm, GroupInvitationForm,
	BorrowerGroupRegistrationForm, BorrowerJoinRequestForm, GroupAdminReviewForm
)
     


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
			return redirect('group_borrower_profile') 
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
			return redirect('group_landing')

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
				return redirect("group_admin_login")

			# ✅ Check if this borrower has "is_group_admin" flag set at registration
			if borrower_profile.is_group_admin:
				login(request, user)
				messages.success(request, "Welcome to your Group Admin Dashboard.")
				return redirect("group_admin_dashboard")
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
		borrower_profile = getattr(request.user, 'borrowerprofile', None)

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
def my_group_dashboard(request):
	"""Borrower sees their group status"""
	borrower = request.user.borrower
	if hasattr(borrower, 'group'):
		group = borrower.group
		return render(request, 'my_group.html', {'group': group})
	else:
		return render(request, 'no_group.html')




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
@login_required
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



def send_group_invite(request, group_id):
	user = request.user.borrower
	group = get_object_or_404(BorrowerGroup, id=group_id, admin=user)
	
	if request.method == "POST":
		form = GroupInvitationForm(request.POST)
		if form.is_valid():
			invite = form.save(commit=False)
			invite.group = group
			invite.invited_by = user
			invite.expires_at = timezone.now() + timezone.timedelta(days=7)
			invite.save()

			# Send SMS
			sms_body = f"Hi {invite.invitee_name}, you’ve been invited to join {group.name}. Use code {invite.invitation_code} or click {request.build_absolute_uri(invite.get_activation_url())}"
			send_sms_smsportal(invite.invitee_phone, sms_body)
			invite.sms_sent = True
			invite.sms_sent_at = timezone.now()
			invite.save()

			# Send Email
			if invite.invitee_email:
				send_mail(
					subject=f"Invitation to join {group.name}",
					message=sms_body,
					from_email=settings.EMAIL_HOST_USER,
					recipient_list=[invite.invitee_email],
				)

			messages.success(request, "Invitation sent successfully!")
			return redirect("groups:group_detail", group_id)
	else:
		form = GroupInvitationForm()

	return render(request, "group_invite.html", {"form": form, "group": group})


def activate_invite(request, code):
    invite = get_object_or_404(GroupInvitation, invitation_code=code, status='pending')

    if invite.expires_at < timezone.now():
        invite.status = 'expired'
        invite.save()
        messages.error(request, "This invitation has expired.")
        return redirect('landing')

    if request.method == 'POST':
        form = ActivationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.save()

            # create or fetch BorrowerProfile and link it
            borrower_profile, created = BorrowerProfile.objects.get_or_create(
                email_address=user.email,
                defaults={'full_name': invite.invitee_name or user.get_full_name(), 'phone_number': invite.invitee_phone}
            )
            borrower_profile.user = user
            borrower_profile.save()

            # add to group membership
            GroupMembership.objects.get_or_create(group=invite.group, borrower=borrower_profile, defaults={'role':'member'})

            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save()

            login(request, user)
            messages.success(request, "Account created and joined the group.")
            return redirect('borrower_index')
    else:
        form = ActivationForm(initial={
			'email': invite.invitee_email or '',
			'phone_number': invite.invitee_phone or '',
			})

    return render(request, 'activate_invite.html', {'invite': invite, 'form': form})


def activate_invite2(request, code):
    invite = get_object_or_404(GroupInvitation, invitation_code=code, status='pending')
    
    if invite.expires_at < timezone.now():
        invite.status = 'expired'
        invite.save()
        messages.error(request, "This invitation has expired.")
        return redirect("landing")

    if request.method == "POST":
        form = ActivationForm(request.POST)
        if form.is_valid():
            user = form.save()
            borrower_profile = BorrowerProfile.objects.get_or_create(
                user=user,
                defaults={
					'phone_number': invite.invitee_phone, 
					'full_name': invite.invitee_name,
					'email_address': invite.invitee_email,
					}
            )[0]
            
            invite.group.members.add(borrower_profile)
            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save()
            
            messages.success(request, "Welcome! You have joined the group.")
            return redirect("groups:my_group_dashboard")
    else:
        form = ActivationForm()
    
    return render(request, "activate_invite.html", {"invite": invite, "form": form})


def group_invite2(request, group_id):
	group = get_object_or_404(BorrowerGroup, id=group_id, admin=request.user.borrower)

	if request.method == 'POST':
		form = GroupInvitationForm(request.POST)
		if form.is_valid():
			invitation = form.save(commit=False)
			invitation.group = group
			invitation.invited_by = request.user.borrower
			invitation.invitation_code = str(uuid.uuid4())[:8].upper()
			invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
			invitation.save()
			messages.success(request, f"Invitation sent to {invitation.invitee_name or invitation.invitee_phone}.")
			return redirect('groups:group_detail', group.id)
	else:
		form = GroupInvitationForm()

	return render(request, 'group_invite.html', {
		'group': group,
		'form': form
	})

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


# -------------------------------------------------------
# 2️⃣ Group admin reviews and manages requests
# -------------------------------------------------------
@login_required
def review_join_request(request, request_id):
	join_request = get_object_or_404(GroupJoinRequest, id=request_id)
	group = join_request.group

	# Only admin or sub-admins can access
	if request.user.borrowerprofile not in [group.admin, *group.sub_admins.all()]:
		messages.error(request, "You are not authorized to review this request.")
		return redirect('groups:group_detail', group_id=group.id)

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

