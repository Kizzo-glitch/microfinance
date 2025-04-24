from django.shortcuts import render, redirect
from django.contrib import messages

#from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from .forms import UserRegistrationForm

from .models import User
from borrowers.models import BorrowerProfile

from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required



def landing(request):
	
	return render(request, 'landing.html', {})



def register(request):
	if request.method == 'POST':
		form = UserRegistrationForm(request.POST)
		if form.is_valid():
			form.save()
			
			username = form.cleaned_data['username']
			password = form.cleaned_data['password1']
			
			role = form.cleaned_data.get('role')

			user = authenticate(username=username, password=password)
			#login(request, user)
			
			# Redirect based on the role
			if role == 'lender':
				login(request, user)
				messages.success(request, f"Account created for {user.username} as a {role}!")
				return redirect('lender_profile')  # Redirect to lender info page
			elif role == 'borrower':
				login(request, user)
				messages.success(request, f"Account created for {user.username} as a {role}!")
				return redirect('borrower_profile') 
			
			#return redirect('landing')  # Redirect to the login page
	else:
		form = UserRegistrationForm()
	return render(request, 'register.html', {'form': form})
	

def borrower_registration(request):
	borrower_form = BorrowerRegistrationForm()
	if request.method == 'POST':
		borrower_form = BorrowerRegistrationForm(request.POST)
		if borrower_form.is_valid():
			borrower_form.save()
			username = borrower_form.cleaned_data['username']
			password = borrower_form.cleaned_data['password1']

			user = authenticate(username=username, password=password)
			login(request, user)
			messages.success(request, ('You have created your Username Successfully - Please complete the form below'))
			return redirect('borrower_login')

		else:
			messages.success(request, ('Whhops, there was a problem registering'))
			return redirect('borrower_registration')
	else:
		return render(request, 'borrower_registration.html', {'borrower_form':borrower_form})



def lender_registration(request):
	lender_form = LenderRegistrationForm()
	if request.method == 'POST':
		lender_form = LenderRegistrationForm(request.POST)
		if lender_form.is_valid():
			lender_form.save()
			username = lender_form.cleaned_data['username']
			password = lender_form.cleaned_data['password1']

			user = authenticate(username=username, password=password)
			login(request, user)
			messages.success(request, ('You have created your Username Successfully - Please complete the form below'))
			return redirect('lender_login')

		else:
			messages.success(request, ('Whhops, there was a problem registering'))
			return redirect('lender_registration')
	else:
		return render(request, 'lender_registration.html', {'lender_form':lender_form})



def borrower_login(request):
	if request.method == "POST":
		username = request.POST['username']
		password = request.POST['password']
		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)

			# Ensure the Profile exists for the user
			profile, created = BorrowerProfile.objects.get_or_create(user=user)


			messages.success(request, ('You have been logged in'))
			return redirect('borrower_index')
		else:
			messages.success(request, ('There was an Error, please try again'))
			return redirect('login')

	else:
		messages.success(request, ('There was an Error, please try again'))
		return render(request, 'login.html', {})



def lender_login(request):
	if request.method == "POST":
		username = request.POST['username']
		password = request.POST['password']
		user = authenticate(request, username=username, password=password)
		if user is not None:
			login(request, user)

			# Ensure the Profile exists for the user
			profile, created = LenderProfile.objects.get_or_create(user=user)

			messages.success(request, ('You have been logged in'))
			return redirect('lender_index')
		else:
			messages.success(request, ('There was an Error, please try again'))
			return redirect('login')


	else:
		messages.success(request, ('There was an Error, please try again'))
		return render(request, 'login.html', {})





def logout_user(request):
	logout(request)
	#messages.success(request, ('You have been logged out'))
	return redirect('landing') 

'''def register(request):
	if request.method == 'POST':
		form = UserRegistrationForm(request.POST)
		if form.is_valid():
			user = form.save()
			role = form.cleaned_data.get('role')
			messages.success(request, f"Account created for {user.username} as a {role}!")
			return redirect('login')  # Redirect to the login page
	else:
		form = UserRegistrationForm()
	return render(request, 'register.html', {'form': form}) '''


class CustomLoginView(LoginView):
	template_name = 'login.html'
	redirect_authenticated_user = True


@login_required
def role_based_redirect(request):
	if request.user.is_lender():
		return redirect('lender_index')  # To lender dashboard 
	elif request.user.is_borrower():
		return redirect('borrower_index')  # To borrower dashboard 
	return redirect('landing')  # Default fallback