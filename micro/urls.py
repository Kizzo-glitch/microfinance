from django.urls import path
from .views import landing, register, CustomLoginView, role_based_redirect, borrower_registration, lender_registration, borrower_login, lender_login, logout_user
from django.contrib.auth import views as auth_views 

urlpatterns = [
	path('', landing, name='landing'),
	
	path('borrower_registration/', borrower_registration, name='borrower_registration'),
	path('lender_registration/', lender_registration, name='lender_registration'),

	path('borrower_login/', borrower_login, name='borrower_login'),
	path('lender_login/', lender_login, name='lender_login'),
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