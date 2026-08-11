
from django.apps import AppConfig

class UssdConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comms.ussd"      # the full import path
    label = "comms_ussd"     # unique label Django uses internally