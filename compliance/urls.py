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
    #path('<int:lender_id>/pay-fee/', views.pay_investigation_fee, name='pay_investigation_fee'),
    path('<int:lender_id>/pay-fee/', views.PayInvestigationFeeView.as_view(), name='pay_investigation_fee'),
    #path('<int:lender_id>/submit/', views.submit_application, name='submit_application'),
    path('<int:lender_id>/submit/', views.SubmitApplicationView.as_view(), name='submit_application'),

    path('<int:lender_id>/receit/', views.submission_receipt, name='submission_receipt'),

    #path('<int:lender_id>/pay-fee/', views.PayInvestigationFeeView.as_view(), name='pay_investigation_fee'),

    

    #path('<int:lender_id>/personnel/add/', views.PersonnelCreateView.as_view(), name='personnel_add'),
    path('<int:lender_id>/personnel/add/', views.PersonnelCreateView.as_view(), name='personnel_create'),
    path('personnel/<int:pk>/edit/', views.PersonnelUpdateView.as_view(), name='personnel_update'),
    path('personnel/<int:pk>/delete/', views.PersonnelDeleteView.as_view(), name='personnel_delete'),

    path('generation-readiness/', views.DocumentGenerationReadinessView.as_view(), name='generation_readiness'),
    path('generate-documents/', views.GenerateDocumentsView.as_view(), name='generate_documents'),
    path('generate-single/<str:document_field>/', views.GenerateSingleDocumentView.as_view(), name='generate_single'),
    path('preview/<str:document_type>/', views.DocumentPreviewView.as_view(), name='document_preview'),
    path('generation-stream/<str:generation_id>/', views.GenerationStreamView.as_view(), name='generation_stream'),

   
]