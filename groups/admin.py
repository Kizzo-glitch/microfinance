from django.contrib import admin
from .models import BorrowerGroup, GroupMembership, GroupInvite, GroupRequest


admin.site.register(BorrowerGroup)
admin.site.register(GroupMembership)
admin.site.register(GroupInvite)
admin.site.register(GroupRequest)
