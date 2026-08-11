from django.apps import AppConfig

class SmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comms.sms"
    label = "comms_sms"