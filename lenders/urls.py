from django.urls import path
from . import views
from .views import LoanApplicationListView, LoanApplicationUpdateView, LoanListView, RejectedLoanListView, FullyPaidLoanListView, LoanStatusUpdateView, ApprovedLoansView, PendingLoansView, RejectedLoansView, OverdueLoansView, FullyPaidLoansView

urlpatterns = [
    path('lender_index/', views.lender_index, name='lender_index'),
    
    path('lender_profile/', views.lender_profile, name='lender_profile'),

    #path('mark_notifications_read/', views.mark_notifications_read, name='mark_notifications_read'),

    path('mark-loan-application-notifications-read/', views.mark_loan_application_notifications_read, name="mark_loan_application_notifications_read"),
    path('mark-loan-payment-notifications-read/', views.mark_loan_payment_notifications_read, name="mark_loan_payment_notifications_read"),


    #path('applied_loans/', views.applied_loans, name='applied_loans'),
    #path('process_loan_application/<int:loan_id>/process/', views.process_loan_application, name='process_loan_application'),


    path('loan-applications/', LoanApplicationListView.as_view(), name='loan-application-list'),
    path('loan-application/<int:pk>/update/', LoanApplicationUpdateView.as_view(), name='loan-application-update'),
    path('loan/<int:pk>/update-status/', LoanStatusUpdateView.as_view(), name='loan-status-update'),
    
    path('loans/', LoanListView.as_view(), name='loan-list'),

    #path('approved-loans/', views.approved_loans, name='approved-loans'),
    path('approved-loans/', ApprovedLoansView.as_view(), name='approved-loans'),
    #path('pending-loans/', views.pending_loans, name='pending-loans'),
    path('pending-loans/', PendingLoansView.as_view(), name='pending-loans'), 
    #path('pending/update/', views.update_pending_loans, name='update-pending-loans'),
    path('rejected-loans/', RejectedLoansView.as_view(), name='rejected-loans'),
    #path('rejected-loans/', views.rejected_loans, name='rejected-loans'),
    path('overdue-loans/', OverdueLoansView.as_view(), name='overdue-loans'), 
    #path('overdue-loans/', views.overdue_loans, name='overdue-loans'),
    path('fully-paid-loans/', FullyPaidLoansView.as_view(), name='fully-paid-loans'),
    #path('fully-paid-loans/', views.fully_paid_loans, name='fully-paid-loans'),
    #path('rejected-loans/', RejectedLoanListView.as_view(), name='rejected-loans'),

    path('loan/<int:loan_id>/payment-history/', views.my_borrower_payment_history, name='my-borrower-payment-history'),

    #path('paid-loans/', FullyPaidLoanListView.as_view(), name='fully_paid_loans'),

    path("lender/risk-customers/<str:category>/", views.risk_customer_list, name="risk_customers"),

    path('lender/dashboard/repayments-data/', views.lender_repayment_data, name='lender_repayment_data'),
    path('lender/dashboard/loan-statuses-data/', views.lender_loan_status_data, name='lender_loan_status_data'),
    path("dashboard/risk-customers/<str:category>/", views.risk_customer_list, name="risk_customer_list"),

   

]