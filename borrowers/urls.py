from django.urls import path
from . import views
from .views import BorrowerNotificationListView 



urlpatterns = [
    path('borrower_index/', views.borrower_index, name='borrower_index'),
   
    path('layout_sidenav_light/', views.layout_sidenav_light, name='layout_sidenav_light'),
    path('layout_static/', views.layout_static, name='layout_static'),
    #path('login/', views.login, name='login'),
    path('password/', views.password, name='password'),
  
    path('tables/', views.tables, name='tables'),
    path('borrower_profile/', views.borrower_profile, name='borrower_profile'),

    path('lender_details/<int:lender_id>/', views.lender_details, name='lender_details'),
    
    path('send-otp/', views.send_otp, name='send_otp'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),

    path('employment-type/', views.select_employment_type, name='employment_type'),
    path('upload_documents_employed/', views.upload_documents_employed, name='upload_documents_employed'),
    path('upload_documents_self_employed/', views.upload_documents_self_employed, name='upload_documents_self_employed'),
    path('upload_documents_registered_business/', views.upload_documents_registered_business, name='upload_documents_registered_business'),
    path('my-documents/', views.view_documents, name='view_documents'),
    path('download-document/<str:document_type>/', views.download_document, name='download_document'),

    path('loan_application/', views.loan_application, name='loan_application'),
    path('apply-loan/', views.apply_loan, name='apply-loan'),
    path('calculate-loan/', views.calculate_loan, name='calculate-loan'),
    path('loan-calculator/', views.loan_calculator, name='loan-calculator'),

    
    path('apply-loan-list/', views.apply_for_loan_list, name='apply-for-loan-list'),
    path('my-loan-applications/', views.my_loan_applications, name='my-loan-applications'),

    path('pending-loan/', views.pending_loan_application, name='pending_loan'),
    path('update-application/<int:application_id>/', views.update_loan_application, name='update_loan_application'),
    path('update-documents/<int:loan_id>/', views.update_documents, name='update_documents'),
    path('delete-application/<int:application_id>/', views.delete_loan_application, name='delete_loan_application'),

    path('my-active-loans/', views.my_active_loans, name='my-active-loans'),


    path('loan-application-success/', views.loan_application_success, name='loan-application-success'),
    path('my-loans-list/', views.my_loan_list, name='my-loan-list'),
    path('loan/<int:loan_id>/', views.loan_details, name='loan-details'),

    #path('record-payment/<int:loan_id>/', views.record_payment, name='record-payment'),

    path('loan/<int:loan_id>/record-payment/', views.record_payment, name='record-payment'),
    path('borrower/payment-history/', views.borrower_payment_history, name='borrower_payment_history'),

    path('mark_loan_approved_read/', views.mark_loan_approved_read, name='mark_loan_approved_read'),
    path('notification/read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    path('borrower-notifications/', BorrowerNotificationListView.as_view(), name='borrower-notifications'),

    path('api/loan-chart-data/', views.loan_chart_data, name='loan_chart_data'),
    path('api/borrower/monthly-repayments/', views.monthly_repayments, name='monthly_repayments'),
    path('api/borrower/balance-over-time/', views.balance_over_time, name='balance_over_time'),
    path('api/borrower/paid-vs-outstanding/', views.paid_vs_outstanding, name='paid_vs_outstanding'),

    

]


