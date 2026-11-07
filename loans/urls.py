from django.urls import path
from . import views


app_name = 'loans'

urlpatterns = [
    path('kfs/<int:kfs_id>/', views.view_kfs, name='view_kfs'), 
    path('kfs/<int:kfs_id>/acknowledge/', views.acknowledge_kfs, name='acknowledge_kfs'),
]