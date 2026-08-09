"""
Fedha-Grow — pending payment adapter
====================================
Honest placeholder for payment rails (mobile money, banks, PSPs) before a real
provider is configured.

A pending payment adapter rejects ALL webhook signatures — with no provider
connected, no authentic callback can exist — and never confirms a payment.
See base.py design rules.
"""

from decimal import Decimal
from ..base import PaymentAdapter, PaymentStatus, PaymentResult

_PENDING_MSG = (
    "{label} integration is provisioned but not yet connected. "
    "Awaiting provider endpoint and credentials."
)


class PendingPaymentAdapter(PaymentAdapter):
    def __init__(self, provider_name: str, label: str):
        self.provider_name = provider_name
        self.label = label

    def initiate(self, *, amount: Decimal, reference: str, payer=None,
                 payee=None, **kwargs) -> PaymentResult:
        return self._result(
            PaymentStatus.PENDING,
            amount=amount,
            reference=reference,
            message=_PENDING_MSG.format(label=self.label),
        )

    def verify_webhook_signature(self, request) -> bool:
        return False  # no provider => no authentic callbacks

    def parse_webhook(self, request) -> PaymentResult:
        return self._result(
            PaymentStatus.PENDING,
            message=_PENDING_MSG.format(label=self.label),
        )