from django.contrib import admin

from .sms.models import SmsLog

admin.site.register(SmsLog)

