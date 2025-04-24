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
    
   
]