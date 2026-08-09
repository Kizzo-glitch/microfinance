"""
Fedha-Grow — pending verification adapter
=========================================
Honest placeholder for verification providers (credit bureau, government
identity, document analysis) before a real provider is configured.

A pending verification adapter NEVER returns verified — absence of a provider
means "not verified", never a fabricated pass. See base.py design rules.
"""

from ..base import VerificationAdapter, VerificationStatus, VerificationResult

_PENDING_MSG = (
    "{label} integration is provisioned but not yet connected. "
    "Awaiting provider endpoint and credentials."
)


class PendingVerificationAdapter(VerificationAdapter):
    def __init__(self, provider_name: str, label: str):
        self.provider_name = provider_name
        self.label = label

    def check(self, identifier: str, **kwargs) -> VerificationResult:
        return self._result(
            VerificationStatus.PENDING,
            message=_PENDING_MSG.format(label=self.label),
            data={"identifier_supplied": bool(identifier)},
        )

