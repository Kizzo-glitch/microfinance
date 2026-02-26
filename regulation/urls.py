
from django.contrib import admin
from django.urls import path
from . import views

app_name = 'regulator'


urlpatterns = [
	path('regulator-profile/', views.regulator_profile, name='regulator_profile'),
    path('dashboard/', views.regulator_dashboard, name='regulator_dashboard'),
    path('review/<int:lender_id>/', views.review_lender, name='review_lender'),
	

] 