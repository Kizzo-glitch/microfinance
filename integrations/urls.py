"""
Fedha-Grow — integrations URLs
Mount in the project urls.py:  path("integrations/", include("integrations.urls"))
"""


from django.urls import path
from . import webhooks
from . import views

app_name = "integrations"

urlpatterns = [
    # Read-only status panel (staff only)
    path("status/", views.integration_status, name="integration_status"),
    #   /integrations/webhooks/mobile_money/
    #   /integrations/webhooks/payment_provider/
    path("webhooks/<str:category>/", webhooks.payment_webhook, name="payment_webhook"),
]