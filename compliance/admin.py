from django.contrib import admin

from .models import ComplianceProfile, PersonnelProfile, ComplianceDocument, ComplianceChecklistItem


admin.site.register(ComplianceProfile)
admin.site.register(PersonnelProfile)
admin.site.register(ComplianceDocument)
admin.site.register(ComplianceChecklistItem)