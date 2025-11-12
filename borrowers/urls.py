from django.urls import path
from . import views
from .views import BorrowerNotificationListView 

app_name = 'borrowers'

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
    path('resume-application/<int:app_id>/', views.resume_application, name='resume_application'),
    #path('resume-application/<int:pk>/', views.resume_application, name='resume_application'),
    path('delete-draft/<int:pk>/', views.delete_draft_application, name='delete_draft_application'),
 
   
    path('upload_documents_employed/', views.upload_documents_employed, name='upload_documents_employed'),
    path('upload_documents_self_employed/', views.upload_documents_self_employed, name='upload_documents_self_employed'),
    path('upload_documents_registered_business/', views.upload_documents_registered_business, name='upload_documents_registered_business'),
    path('my-documents/', views.view_documents, name='view_documents'),
    path('download-document/<str:document_type>/', views.download_document, name='download_document'),

    path('update-expenses/', views.update_expenses, name='update_expenses'),

    path('loan_application/', views.loan_application, name='loan_application'),
    path('apply-loan/', views.apply_loan, name='apply-loan'),
    path('calculate-loan/', views.calculate_loan, name='calculate-loan'),
    path('loan-calculator/', views.loan_calculator, name='loan-calculator'),

    
    path('apply-loan-list/', views.apply_for_loan_list, name='apply-for-loan-list'),
    

    path('pending-loan/', views.pending_loan_application, name='pending_loan'),
    path('update-application/<int:application_id>/', views.update_loan_application, name='update_loan_application'),
    path('update-documents/<int:loan_id>/', views.update_documents, name='update_documents'),
    path('delete-application/<int:application_id>/', views.delete_loan_application, name='delete_loan_application'),

    path('my-loans-list/', views.my_loan_list, name='my_loan_list'),
    path('my-active-loans/', views.my_active_loans, name='my_active_loans'),
    path('my-loan-applications/', views.my_loan_applications, name='my_loan_applications'),


    path('loan-application-success/', views.loan_application_success, name='loan-application-success'),
    
    path('loan/<int:loan_id>/', views.loan_details, name='loan-details'),

    path('loan/<int:loan_id>/record-payment/', views.record_payment, name='record-payment'),
    path('borrower/payment-history/', views.borrower_payment_history, name='borrower_payment_history'),

    path('mark_loan_approved_read/', views.mark_loan_approved_read, name='mark_loan_approved_read'),
    path('mark_loan_rejected_read/', views.mark_loan_rejected_read, name='mark_loan_rejected_read'),
    path('mark_loan_pending_read/', views.mark_loan_pending_read, name='mark_loan_pending_read'),

    path('notification/read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    path('borrower-notifications/', BorrowerNotificationListView.as_view(), name='borrower-notifications'),

    path('api/loan-chart-data/', views.loan_chart_data, name='loan_chart_data'),
    path('api/borrower/monthly-repayments/', views.monthly_repayments, name='monthly_repayments'),
    path('api/borrower/balance-over-time/', views.balance_over_time, name='balance_over_time'),
    path('api/borrower/paid-vs-outstanding/', views.paid_vs_outstanding, name='paid_vs_outstanding'),

    path('my-groups-dashboard/', views.borrower_groups_dashboard, name='borrower_groups_dashboard'),
    path('<int:group_id>/', views.borrower_group_detail, name='borrower_group_detail'),
    path('join-group/<int:group_id>/', views.borrower_join_group, name='borrower_join_group'),
    path('<int:group_id>/manage-members/', views.admin_manage_members, name='admin_manage_members'),
    path('<int:group_id>/activity/', views.group_activity_log, name='group_activity_log'),
    path('<int:group_id>/documents/', views.group_documents, name='group_documents'),
    


    
    # Groups
    #path("groups/", views.my_groups, name="my_groups"),
    #path("create/", views.create_group, name="create_group"),
    #path("<int:group_id>/", views.group_detail, name="group_detail"),
    #path("<int:group_id>/invite/", views.invite_member, name="invite_member"),
    #path("join/<uuid:token>/", views.join_group, name="join_group"),

    # member management
    #path("membership/<int:membership_id>/make-subadmin/", views.make_sub_admin, name="make_sub_admin"),
    #path("membership/<int:membership_id>/make-member/", views.make_member, name="make_member"),
    #path("membership/<int:membership_id>/remove/", views.remove_member, name="remove_member"),

    # invites management
    #path("invite/<int:invite_id>/resend/", views.resend_invite, name="resend_invite"),
    #path("invite/<int:invite_id>/revoke/", views.revoke_invite, name="revoke_invite"),

]


