from django.urls import path
from .views import *

app_name = 'compliance'

urlpatterns = [
  
    path('compliance-dashboard/', ComplianceDashboardView.as_view, name='compliance_dashboard'),
    

    path('wizard/tier/', ComplianceTierSelectionView.as_view(), name='tier'),
    path('wizard/company/', ComplianceCompanyInfoView.as_view(), name='company-info'),
    path('wizard/directors/', ComplianceDirectorsView.as_view(), name='directors'),
    path('wizard/governance/', ComplianceGovernanceView.as_view(), name='governance'),
    path('wizard/documents/', ComplianceDocumentsView.as_view(), name='documents'),
    path('wizard/review/', ComplianceReviewView.as_view(), name='review'), 

    path('wizard/', ComplianceWizardResumeView.as_view(), name='wizard_resume'),

]



