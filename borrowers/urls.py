from django.urls import path
from . import views
from .views import BorrowerNotificationListView 

urlpatterns = [
    path('borrower_index/', views.borrower_index, name='borrower_index'),
    #path('charts/', views.charts, name='charts'),
    path('layout_sidenav_light/', views.layout_sidenav_light, name='layout_sidenav_light'),
    path('layout_static/', views.layout_static, name='layout_static'),
    #path('login/', views.login, name='login'),
    path('password/', views.password, name='password'),
    #path('register/', views.register, name='register'),
    path('tables/', views.tables, name='tables'),
    path('borrower_profile/', views.borrower_profile, name='borrower_profile'),
    path('upload_documents/', views.upload_documents, name='upload_documents'),
    path('loan_application/', views.loan_application, name='loan_application'),
    path('lender_details/<int:lender_id>/', views.lender_details, name='lender_details'),

    path('calculate-loan/', views.calculate_loan, name='calculate-loan'),
    path('loan-calculator/', views.loan_calculator, name='loan-calculator'),

    path('apply-loan/', views.apply_loan, name='apply-loan'),
    path('apply-loan-list/', views.apply_for_loan_list, name='apply-for-loan-list'),
    path('my-loan-applications/', views.my_loan_applications, name='my-loan-applications'),
    path('my-active-loans/', views.my_active_loans, name='my-active-loans'),


    path('loan-application-success/', views.loan_application_success, name='loan-application-success'),
    path('my-loans-list/', views.my_loan_list, name='my-loan-list'),
    path('loan/<int:loan_id>/', views.loan_details, name='loan-details'),

    #path('record-payment/<int:loan_id>/', views.record_payment, name='record-payment'),

    path('loan/<int:loan_id>/record-payment/', views.record_payment, name='record-payment'),
    path('borrower/payment-history/', views.borrower_payment_history, name='borrower_payment_history'),

    path('mark_loan_approved_read/', views.mark_loan_approved_read, name='mark_loan_approved_read'),

    path('api/loan-chart-data/', views.loan_chart_data, name='loan_chart_data'),

    #path('api/monthly-repayments/', views.monthly_repayments, name='monthly_repayments'),
    #path('api/balance-over-time/', views.balance_over_time, name='balance_over_time'),
    #path('api/paid-vs-outstanding/', views.paid_vs_outstanding, name='paid_vs_outstanding'),

    path('api/borrower/monthly-repayments/', views.monthly_repayments, name='monthly_repayments'),
    path('api/borrower/balance-over-time/', views.balance_over_time, name='balance_over_time'),
    path('api/borrower/paid-vs-outstanding/', views.paid_vs_outstanding, name='paid_vs_outstanding'),

    path('borrower/notifications/', BorrowerNotificationListView.as_view(), name='borrower-notifications'),

]


