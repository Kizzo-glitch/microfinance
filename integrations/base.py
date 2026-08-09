"""
Fedha-Grow — integrations layer (base)
======================================
Adapter pattern for external providers. The application talks to a stable
interface; the concrete provider sits behind it. Until a real URL + credentials
are configured, an honest "PENDING" adapter is used.

DESIGN SAFETY RULES (do not weaken):
  1. A pending/unconfigured verification NEVER returns a positive result.
     Absence of a provider means "not verified", never "verified".
  2. Adapters never fabricate provider responses. PENDING is a real state,
     surfaced honestly, not a fake success.
  3. Every result carries a reference + timestamp so it reconciles to source.

Two adapter shapes:
  - VerificationAdapter : request -> status   (credit bureau, government identity)
  - PaymentAdapter      : initiate + webhook  (mobile money, banks, PSPs)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid
from django.utils import timezone


# =====================================================================
# Result status enums
# =====================================================================
class VerificationStatus(str, Enum):
    VERIFIED     = "verified"       # provider confirmed a positive match
    NOT_VERIFIED = "not_verified"   # provider ran and did NOT confirm
    PENDING      = "pending"        # provider not connected / awaiting integration
    ERROR        = "error"          # provider connected but the call failed


class PaymentStatus(str, Enum):
    INITIATED = "initiated"   # request accepted by provider, awaiting settlement
    CONFIRMED = "confirmed"   # webhook confirmed funds moved
    FAILED    = "failed"      # provider reported failure
    PENDING   = "pending"     # provider not connected / awaiting integration
    ERROR     = "error"       # connected but the call failed


# =====================================================================
# Result value objects
# =====================================================================
@dataclass
class VerificationResult:
    status: VerificationStatus
    provider: str
    reference: str = field(default_factory=lambda: uuid.uuid4().hex)
    data: dict = field(default_factory=dict)
    message: str = ""
    checked_at: str = field(default_factory=lambda: timezone.now().isoformat())

    @property
    def is_verified(self) -> bool:
        # ONLY an explicit VERIFIED counts. Pending/error never pass.
        return self.status == VerificationStatus.VERIFIED

    @property
    def is_pending(self) -> bool:
        return self.status == VerificationStatus.PENDING


@dataclass
class PaymentResult:
    status: PaymentStatus
    provider: str
    reference: str = field(default_factory=lambda: uuid.uuid4().hex)
    amount: Optional[Decimal] = None
    data: dict = field(default_factory=dict)
    message: str = ""
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())

    @property
    def is_confirmed(self) -> bool:
        return self.status == PaymentStatus.CONFIRMED

    @property
    def is_pending(self) -> bool:
        return self.status == PaymentStatus.PENDING


# =====================================================================
# Base adapters
# =====================================================================
class VerificationAdapter:
    """
    Base for request/response verification providers
    (credit bureau, government identity).
    """
    provider_name: str = "generic-verification"

    def check(self, identifier: str, **kwargs) -> VerificationResult:
        raise NotImplementedError

    # convenience for building results
    def _result(self, status: VerificationStatus, **kw) -> VerificationResult:
        return VerificationResult(status=status, provider=self.provider_name, **kw)


class PaymentAdapter:
    """
    Base for payment rails (mobile money, banks, PSPs). Two directions:
      - initiate(): outbound request to move money
      - handle_webhook(): inbound callback confirming settlement
    """
    provider_name: str = "generic-payment"

    def initiate(self, *, amount: Decimal, reference: str, payer=None,
                 payee=None, **kwargs) -> PaymentResult:
        raise NotImplementedError

    def verify_webhook_signature(self, request) -> bool:
        """Return True only if the callback is authentically from the provider."""
        raise NotImplementedError

    def parse_webhook(self, request) -> PaymentResult:
        """Turn an authenticated callback into a PaymentResult."""
        raise NotImplementedError

    def _result(self, status: PaymentStatus, **kw) -> PaymentResult:
        return PaymentResult(status=status, provider=self.provider_name, **kw)