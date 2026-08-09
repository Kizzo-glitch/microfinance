"""
Fedha-Grow — provider registry
===============================
Single place that decides which adapter answers for each category. Driven by
settings: if a provider is configured (URL + credentials present), its live
adapter is used; otherwise the honest PendingAdapter is returned.

Going live with a real provider is a two-step change, no application rewrites:
  1. add the live adapter class (e.g. integrations/providers/mopay.py)
  2. set its config in settings.INTEGRATIONS

Example settings block:

    INTEGRATIONS = {
        "credit_bureau": {
            "label": "Credit bureau",
            "adapter": "integrations.providers.compuscan.CompuscanAdapter",
            "config": {"base_url": "...", "api_key": "..."},
        },
        "government_identity": {"label": "Home Affairs ID", "adapter": None},
        "mobile_money":       {"label": "Mobile money",    "adapter": None},
        "payment_provider":   {"label": "Payment provider","adapter": None},
    }

adapter=None (or a missing/blank config) => PendingAdapter for that category.
"""

from django.conf import settings
from django.utils.module_loading import import_string

#from .base import VerificationAdapter, PaymentAdapter
#from .pending import PendingVerificationAdapter, PendingPaymentAdapter

from .verification.pending import PendingVerificationAdapter
from .payments.pending import PendingPaymentAdapter


# Category -> which base shape it uses.
_VERIFICATION_CATEGORIES = {"credit_bureau", "government_identity"}
_PAYMENT_CATEGORIES = {"mobile_money", "bank", "payment_provider"}

# Sensible default labels if settings doesn't override them.
_DEFAULT_LABELS = {
    "credit_bureau": "Credit bureau",
    "government_identity": "Home Affairs ID",
    "mobile_money": "Mobile money",
    "bank": "Bank rails",
    "payment_provider": "Payment provider",
}


def _category_config(category: str) -> dict:
    return (getattr(settings, "INTEGRATIONS", {}) or {}).get(category, {}) or {}


def _label(category: str) -> str:
    return _category_config(category).get("label") or _DEFAULT_LABELS.get(category, category)


def _is_configured(cfg: dict) -> bool:
    """A provider is live only if an adapter path AND some config are present."""
    return bool(cfg.get("adapter")) and bool(cfg.get("config"))


def get_adapter(category: str):
    """
    Return the adapter for a category — live if configured, else pending.
    Raises ValueError for an unknown category (fail loud on typos).
    """
    if category not in _VERIFICATION_CATEGORIES and category not in _PAYMENT_CATEGORIES:
        raise ValueError(f"Unknown integration category: {category!r}")

    cfg = _category_config(category)
    label = _label(category)
    provider_name = cfg.get("provider_name") or category

    if _is_configured(cfg):
        adapter_cls = import_string(cfg["adapter"])
        return adapter_cls(**cfg.get("config", {}))

    # Not configured -> honest pending adapter of the right shape.
    if category in _VERIFICATION_CATEGORIES:
        return PendingVerificationAdapter(provider_name=provider_name, label=label)
    return PendingPaymentAdapter(provider_name=provider_name, label=label)


def provider_status() -> dict:
    """
    Category -> {'label', 'connected'} for every known integration.
    Feeds an admin/status view so you can see at a glance what's live.
    """
    out = {}
    for category in (_VERIFICATION_CATEGORIES | _PAYMENT_CATEGORIES):
        cfg = _category_config(category)
        out[category] = {"label": _label(category), "connected": _is_configured(cfg)}
    return out