from django.urls import path

from .views import (
		landing, register, CustomLoginView, 
		role_based_redirect, lender_compliance,
		logout_user
    )
from django.contrib.auth import views as auth_views 

urlpatterns = [
	path('', landing, name='landing'),
	
	path('lender_compliance/', lender_compliance, name='lender_compliance'),
	
	
	path('logout/', logout_user, name='logout'),

	path('register/', register, name='register'),
	path('login/', CustomLoginView.as_view(), name='login'),
	path('redirect/', role_based_redirect, name='role_based_redirect'),

	path('password-reset/', 
		auth_views.PasswordResetView.as_view(
			template_name='password_reset.html'
		), 
		name='password_reset'),

	path('password-reset/done/', 
		auth_views.PasswordResetDoneView.as_view(
			template_name='password_reset_done.html'
		), 
		name='password_reset_done'),

	path('reset/<uidb64>/<token>/', 
		auth_views.PasswordResetConfirmView.as_view(
			template_name='password_reset_confirm.html'
		), 
		name='password_reset_confirm'),

	path('reset/done/', 
		auth_views.PasswordResetCompleteView.as_view(
			template_name='password_reset_complete.html'
		), 
		name='password_reset_complete'),
	
   
]