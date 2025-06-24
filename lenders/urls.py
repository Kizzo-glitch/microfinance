from django.urls import path
from . import views
from .views import (
    LoanApplicationListView, 
    LoanApplicationUpdateView, 
    LoanListView, RejectedLoanListView, 
    FullyPaidLoanListView, LoanStatusUpdateView, 
    ApprovedLoansView, PendingLoansView, RejectedLoansView, 
    OverdueLoansView, FullyPaidLoansView, LenderVerificationListView, 
    LenderVerificationDetailView, LenderNotificationListView,
    )


urlpatterns = [
    path('lender_index/', views.lender_index, name='lender_index'),
    
    path('lender_profile/', views.lender_profile, name='lender_profile'),

    # Lender Documents
    path('upload-lender-docs/', views.upload_lender_docs, name='upload_lender_docs'),
    path('my-documents/', views.view_lender_documents, name='view_lender_documents'),
    path('download-lender-document/<str:document_type>/', views.download_lender_document, name='download_lender_document'),
    path('update-lender-docs/', views.update_lender_documents, name='update_lender_documents'),

    # Top-bar notifications
    path('mark-loan-application-notifications-read/', views.mark_loan_application_notifications_read, name="mark_loan_application_notifications_read"),
    path('mark-loan-payment-notifications-read/', views.mark_loan_payment_notifications_read, name="mark_loan_payment_notifications_read"),
    path('notifications/mark-pending-loan-updates-read/', views.mark_pending_loan_update_notifications_read, name='mark_pending_loan_update_notifications_read'),

    # Side-bar notification
    #path('mark_loan_approved_read/', views.mark_loan_approved_read, name='mark_loan_approved_read'),
    path('notification/read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'), 
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    path('lender_notifications/', LenderNotificationListView.as_view(), name='lender_notifications'),


    #path('applied_loans/', views.applied_loans, name='applied_loans'),
    #path('process_loan_application/<int:loan_id>/process/', views.process_loan_application, name='process_loan_application'),

    path('loan-applications/', LoanApplicationListView.as_view(), name='loan-application-list'),
    path('loan-application/<int:pk>/update/', LoanApplicationUpdateView.as_view(), name='loan-application-update'),
    path('loan/<int:pk>/update-status/', LoanStatusUpdateView.as_view(), name='loan-status-update'),
    path('loan/update-pending-loans/', views.update_pending_loans, name='update-pending-loans'),
    
    path('loans/', LoanListView.as_view(), name='loan-list'),

    
    path('approved-loans/', ApprovedLoansView.as_view(), name='approved-loans'),
    path('pending-loans/', PendingLoansView.as_view(), name='pending-loans'), 
    path('rejected-loans/', RejectedLoansView.as_view(), name='rejected-loans'),
    path('overdue-loans/', OverdueLoansView.as_view(), name='overdue-loans'), 
    path('fully-paid-loans/', FullyPaidLoansView.as_view(), name='fully-paid-loans'),


    path('loan/<int:loan_id>/payment-history/', views.my_borrower_payment_history, name='my-borrower-payment-history'),


    path("lender/risk-customers/<str:category>/", views.risk_customer_list, name="risk_customers"),

    path('lender/dashboard/repayments-data/', views.lender_repayment_data, name='lender_repayment_data'),
    path('lender/dashboard/loan-statuses-data/', views.lender_loan_status_data, name='lender_loan_status_data'),
    path("dashboard/risk-customers/<str:category>/", views.risk_customer_list, name="risk_customer_list"),

    path('my-clients/', views.my_clients, name='my_clients'),
    path('lender/loan/<int:loan_id>/documents/', views.borrower_documents, name='view_borrower_documents'),

    path('credit-reports/', views.credit_reports, name='credit_reports'),

    path('admin/lender-verifications/', LenderVerificationListView.as_view(), name='lender_verification_list'),
    path('admin/lender-verifications/<int:pk>/', LenderVerificationDetailView.as_view(), name='lender_verification_detail'),


]