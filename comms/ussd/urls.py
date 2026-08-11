"""
Fedha-Grow — USSD URLs
Mount in project urls.py:  path("ussd/", include("ussd.urls"))
The MNO/aggregator shortcode is pointed at /ussd/callback/ once provisioned.
"""
from django.urls import path
from . import views

app_name = "ussd"

urlpatterns = [
    path("callback/", views.ussd_callback, name="callback"),
]