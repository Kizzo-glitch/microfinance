from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from datetime import date
from django.db import models
from .models import BorrowerGroup, GroupInvite
from django.contrib import messages
from .forms import BorrowerGroupForm, BorrowerGroupRegistrationForm
from borrowers.forms import BorrowerProfileForm
from borrowers.models import BorrowerProfile
from loans.models import LoanApplication, Loan, LoanPayment, Notification, Rating




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
				return redirect('group_admin_dashboard')
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
	return redirect('group_landing')




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



def group_admin_dashboard(request):
	current_user = BorrowerProfile.objects.get(user__id=request.user.id)
	if current_user.is_group_admin:
		groups = BorrowerGroup.objects.filter(admin=request.user.borrower) | BorrowerGroup.objects.filter(sub_admins=request.user.borrower)
		return render(request, "group_admin_dashboard.html", {"groups": groups})
	else:
		messages.error(request, "You are not authorized as a Group Admin.")


def admin_logout(request):
	logout(request)
	messages.success(request, ('You have been logged out'))
	return redirect('groups_landing') 


def create_group(request):
	# Prevent users from creating multiple groups if they are already an admin
	current_user = BorrowerProfile.objects.get(user__id=request.user.id)
	if current_user.is_group_admin:
		existing_groups = BorrowerGroup.objects.filter(admin=request.user.borrower)
		if existing_groups.exists():
			messages.error(request, "You already manage a group. You cannot create another one.")
			return redirect("group_detail", group_id=existing_groups.first().id)

		if request.method == "POST":
			form = BorrowerGroupForm(request.POST)
			if form.is_valid():
				group = form.save(commit=False)
				group.created_by = request.user.borrower
				group.save()
				group.admins.add(request.user.borrower)
				messages.success(request, f"Group '{group.name}' created successfully!")
				return redirect("group_detail", group_id=group.id)
		else:
			form = BorrowerGroupForm()
		return render(request, "create_group.html", {"form": form})

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



@login_required
def join_group_by_code(request, code):
	"""Borrower joins a group via invite link"""
	invite = get_object_or_404(GroupInvite, code=code, is_used=False)
	borrower = request.user.borrowerprofile
	invite.group.members.add(borrower)
	invite.is_used = True
	invite.save()
	return redirect('my_group_dashboard')


@login_required
def explore_groups(request):
	"""Lenders see list of groups"""
	if not hasattr(request.user, 'lenderprofile'):
		return redirect('groups_landing')
	groups = BorrowerGroup.objects.filter(is_verified=True)
	return render(request, 'groups_explore.html', {'groups': groups})


def group_detail(request, group_id):
	"""Public group detail (basic info)"""
	group = get_object_or_404(BorrowerGroup, id=group_id)
	return render(request, 'group_detail.html', {'group': group})


def activate_invite2(request, code):
	invite = get_object_or_404(GroupInvite, code=code, is_used=False)
	borrower_profile = invite.group.members.filter(email=invite.email).first()

	if request.method == "POST":
		form = UserRegistrationForm(request.POST)
		if form.is_valid():
			user = form.save(force_role="borrower")  # 👈 force borrower role
			user.email = invite.email
			user.save()

			borrower_profile.user = user
			borrower_profile.save()

			invite.is_used = True
			invite.save()

			login(request, user)
			messages.success(request, "Your borrower account has been activated and linked to the group.")
			return redirect("borrower_index")
	else:
		form = UserRegistrationForm()

	return render(request, "groups/activate_invite.html", {"form": form, "invite": invite})


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

	return render(request, "activate_invite.html", {"form": form, "invite": invite})

