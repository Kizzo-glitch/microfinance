from django.urls import path
from . import views

app_name = 'compliance'


urlpatterns = [
    # Institutional
    path('<int:lender_id>/compliance-dashboard/', views.ComplianceProfileDetailView.as_view(), name='compliance_detail'),
    #path('<int:lender_id>/compliance-update/', views.ComplianceUpdateView.as_view(), name='compliance_update'),
    path('<int:lender_id>/compliance-update/', views.ComplianceUpdateView.as_view(), name='compliance_update'),
    #path('<int:pk>/personnel-update/', views.personnel_update, name='personnel_update'),

    # Personnel
    path('<int:lender_id>/personnel/', views.PersonnelListView.as_view(), name='personnel_list'),
    path('<int:pk>/submit/', views.submit_application, name='submit_application'),



    #path('<int:lender_id>/personnel/add/', views.PersonnelCreateView.as_view(), name='personnel_add'),
    path('personnel/<int:pk>/edit/', views.PersonnelUpdateView.as_view(), name='personnel_update'),
    path('personnel/<int:pk>/delete/', views.PersonnelDeleteView.as_view(), name='personnel_delete'),

    # Quick add (optional)
    path('<int:lender_id>/personnel/quick-add/', views.add_personnel_quick, name='personnel_quick_add'),
]