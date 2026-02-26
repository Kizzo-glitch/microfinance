from django.shortcuts import render, redirect
from django.contrib import messages

#from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from .forms import UserRegistrationForm

from .models import User
from borrowers.models import BorrowerProfile
from lenders.models import LenderProfile

from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required

from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy




def landing(request):	
	return render(request, 'landing.html', {})

def lender_compliance(request):	
	return render(request, 'lender_compliance.html', {})


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
				return redirect('lenders:lender_profile')  # Redirect to lender info page
			elif role == 'borrower':
				login(request, user)
				messages.success(request, f"Account created for {user.username} as a {role}!")
				return redirect('borrowers:borrower_profile') 
			
			#return redirect('landing')  # Redirect to the login page
	else:
		form = UserRegistrationForm()
	return render(request, 'register.html', {'form': form})
	


class RegulatorPasswordChangeView(PasswordChangeView):
    template_name = 'password_setup.html'
    
    def get_success_url(self):
        # Redirect to the profile update page after success
        return reverse_lazy('regulator:regulator_profile')

    def form_valid(self, form):
        user = self.request.user
        user.must_change_password = False
        user.save()
        return super().form_valid(form)

"""
class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'password_change_form.html'
    success_url = reverse_lazy('regulator:regulator_dashboard') # Redirect after change

    def form_valid(self, form):
        # When they successfully change the password, flip the flag to False
        self.request.user.must_change_password = False
        self.request.user.save()
        return super().form_valid(form)


class RegulatorPasswordChangeView(PasswordChangeView):
    template_name = 'password_setup.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        # Once the password is changed, they are no longer forced to change it
        user = self.request.user
        user.must_change_password = False
        user.save()
        return super().form_valid(form)
"""

def logout_user(request):
	logout(request)
	#messages.success(request, ('You have been logged out'))
	return redirect('landing') 




class CustomLoginView(LoginView):
	template_name = 'login.html'
	redirect_authenticated_user = True


@login_required
def role_based_redirect(request):
	if request.user.is_lender:
		return redirect('lenders:lender_index')  # To lender dashboard 
	elif request.user.is_borrower:
		return redirect('borrowers:borrower_index')  # To borrower dashboard 
	return redirect('landing')  # Default fallback


	