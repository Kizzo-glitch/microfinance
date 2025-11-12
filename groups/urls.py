# groups/urls.py
from django.urls import path
from . import views
from .views import GroupTypeSpecificSettingsView

app_name = 'groups'

urlpatterns = [

    path('group-landing/', views.group_landing, name='groups_landing'), 
    path('group-admin-register/', views.register_group_admin, name='register_group_admin'),
    path('group-admin-profile/', views.group_borrower_profile, name='group_borrower_profile'),

    path('group-admin-login/', views.group_admin_login, name='group_admin_login'),   
    path('admin-logout/', views.admin_logout, name='admin_logout'),           
    path('admin-dashboard/', views.group_admin_dashboard, name='group_admin_dashboard'),

    path('group_list', views.group_list, name='group_list'),
    path('create/', views.group_create, name='group_create'),
    path('<int:pk>/group-detail', views.group_detail, name='group_detail'),
    path('<int:pk>/edit/', views.group_edit, name='group_edit'),
    path('<int:group_id>/constitution/', views.group_constitution, name='group_constitution'),
    path('<int:group_id>/settings/', GroupTypeSpecificSettingsView.as_view(), name='group_type_settings'),

    path('<int:group_id>/members/', views.group_members, name='group_members'),
    path('<int:group_id>/manage-sub-admins/', views.manage_sub_admins, name='manage_sub_admins'),
    path('<int:group_id>/manage-members/', views.manage_members, name='manage_members'),
    path('<int:group_id>/activity/', views.group_activity_log, name='group_activity_log'),
    path('<int:group_id>/documents/', views.group_documents, name='group_documents'),
 
    
    path("<int:group_id>/invite/", views.send_group_invite, name="group_invite"),
    path("invite/<str:code>/activate/", views.activate_invite, name="activate_invite"),
    path('<int:request_id>/review/', views.review_join_request, name='review_join_request'),
    path('join-requests/', views.pending_join_requests, name='pending_join_requests'),

    path('join-requests/<int:request_id>/approve/', views.approve_join_request, name='approve_join_request'),
    path('join-requests/<int:request_id>/decline/', views.decline_join_request, name='decline_join_request'),

    path('api/borrowers/has_profile/<int:user_id>/', views.has_borrower_profile, name='has_borrower_profile'),

    # Invitation actions
    
    #path('invitation/<int:invitation_id>/', views.invitation_detail, name='invitation_detail'),
    #path('invitation/<int:invitation_id>/withdraw/', views.withdraw_invitation, name='withdraw_invitation'),
    #path('invitation/<int:invitation_id>/resend/', views.resend_invitation, name='resend_invitation'),
    #path('invitation/<int:invitation_id>/extend/', views.extend_invitation, name='extend_invitation'),
    #path('invitation/<int:invitation_id>/decline/', views.cancel_invitation_activation, name='decline_invitation'),
    


    
    


    #path('invite/<str:code>/', views.join_group_by_code, name='join_group'),   # /groups/invite/ABC123
    #path('explore/', views.explore_groups, name='explore_groups'),   # /groups/explore (for lenders)
    #path('<int:group_id>/', views.group_detail, name='group_detail'), # /groups/12

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
