from django.contrib import admin
from .models import (
    BorrowerGroup, GroupTypeSpecificSettings, 
    GroupConstitution, GroupMembership, GroupInvitation, 
    GroupJoinRequest, LenderGroupSubscription, GroupActivity, GroupDocument) 

#BorrowerGroup, GroupMembership, GroupJoinRequest, GroupRequest


admin.site.register(BorrowerGroup)
admin.site.register(GroupMembership)
admin.site.register(GroupTypeSpecificSettings)
admin.site.register(GroupConstitution)
admin.site.register(GroupInvitation)
admin.site.register(GroupJoinRequest)
admin.site.register(LenderGroupSubscription)
admin.site.register(GroupActivity)
admin.site.register(GroupDocument)
