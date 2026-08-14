
"""
Fedha-Grow — integrations status view
=====================================
A read-only panel showing each integration category and whether a live provider
is connected. Backed by registry.provider_status(). Staff-only.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .registry import provider_status


_GROUPS = [
    ("Verification", ["credit_bureau", "government_identity", "document_analysis"]),
    ("Payments",     ["mobile_money", "bank", "payment_provider"]),
    ("Messaging",    ["sms", "whatsapp", "ussd"]),
]


@staff_member_required
def integration_status(request):
    status = provider_status()  # {category: {'label', 'connected'}}

    groups = []
    for group_label, categories in _GROUPS:
        items = [
            {
                "category": c,
                "label": status.get(c, {}).get("label", c),
                "connected": status.get(c, {}).get("connected", False),
            }
            for c in categories
            if c in status
        ]
        groups.append({"label": group_label, "items": items})

    connected_count = sum(1 for v in status.values() if v["connected"])
    total_count = len(status)

    return render(request, "status.html", {
        "groups": groups,
        "connected_count": connected_count,
        "total_count": total_count,
    })