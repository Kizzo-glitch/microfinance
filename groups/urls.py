# groups/urls.py
from django.urls import path
from . import views

urlpatterns = [

    path('group-landing/', views.group_landing, name='groups_landing'), 
    path('group-admin-register/', views.register_group_admin, name='register_group_admin'),
    path('group-admin-profile/', views.group_borrower_profile, name='group_borrower_profile'),

    path('group-admin-login/', views.group_admin_login, name='group_admin_login'),
    
    path('admin-logout/', views.admin_logout, name='admin_logout'),

    path('create/', views.create_group, name='create_group'), 
              
    path('my-group/', views.my_group_dashboard, name='my_group_dashboard'), 
            
    path('admin/', views.group_admin_dashboard, name='group_admin_dashboard'), 
    path('invite/<str:code>/', views.join_group_by_code, name='join_group'),   # /groups/invite/ABC123
    path('explore/', views.explore_groups, name='explore_groups'),   # /groups/explore (for lenders)
    path('<int:group_id>/', views.group_detail, name='group_detail'), # /groups/12

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
