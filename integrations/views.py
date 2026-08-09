
"""
Fedha-Grow — integrations status view
=====================================
A read-only panel showing each integration category and whether a live provider
is connected. Backed by registry.provider_status(). Staff-only.

Mount in integrations/urls.py:
    path("status/", views.integration_status, name="integration_status"),
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .registry import provider_status


# Group categories the way the interoperability slide does, so the panel reads
# the same way the CBL saw it.
_GROUPS = [
    ("Verification", ["credit_bureau", "government_identity"]),
    ("Payments",     ["mobile_money", "bank", "payment_provider"]),
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