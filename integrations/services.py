"""
Fedha-Grow — integrations service facade
========================================
Thin, friendly entry points so application code never touches adapters or the
registry directly. Import these, not the internals.

    from integrations.services import verify_identity, check_credit_bureau, initiate_payment

Every call works today: with no provider connected it returns a PENDING result,
which callers must treat as "not verified / not settled" — never as success.
"""

from decimal import Decimal
from .registry import get_adapter
from .base import VerificationResult, PaymentResult


# ---- verification -------------------------------------------------
def verify_identity(national_id: str, **kwargs) -> VerificationResult:
    """Government identity (Home Affairs) check."""
    return get_adapter("government_identity").check(national_id, **kwargs)


def check_credit_bureau(identifier: str, **kwargs) -> VerificationResult:
    """Credit-bureau lookup."""
    return get_adapter("credit_bureau").check(identifier, **kwargs)


# ---- payment ------------------------------------------------------
def initiate_payment(category: str, *, amount: Decimal, reference: str,
                     payer=None, payee=None, **kwargs) -> PaymentResult:
    """
    Start an outbound payment on a rail: 'mobile_money', 'bank',
    or 'payment_provider'.
    """
    return get_adapter(category).initiate(
        amount=amount, reference=reference, payer=payer, payee=payee, **kwargs
    )