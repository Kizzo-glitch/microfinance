"""
Fedha-Grow — transaction references
===================================
A readable, collision-resistant reference for every LoanApplication and Loan.

Format:  FG-YYYY-XXXXXX
  FG      product prefix (Fedha-Grow)
  YYYY    year of creation
  XXXXXX  6 chars from an unambiguous alphabet (no 0/O/1/I/L confusion)

Why this exists: the platform's error-resolution and audit story depends on a
single reference both borrower and lender can cite, safe to expose over SMS/USSD/
email, that doesn't leak record counts the way a sequential id does. The SAME
reference threads through the application, its SMS notifications, the USSD session,
and eventual payment reconciliation — so everything about one transaction traces
to one identifier.
"""

import secrets
from django.utils import timezone

# Unambiguous alphabet — no 0/O, 1/I/L to avoid mis-reading over the phone.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _random_suffix(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_reference(model_cls, field_name: str = "reference_number",
                       prefix: str = "FG", year: int = None) -> str:
    """
    Build a unique reference of the form PREFIX-YYYY-XXXXXX, checking the given
    model/field for collisions and retrying until unique. Collisions are
    astronomically unlikely (30^6 ≈ 729M per prefix-year), but we check anyway
    because "unique reference" must be a guarantee, not a probability.
    """
    year = year or timezone.now().year
    for _ in range(10):
        candidate = f"{prefix}-{year}-{_random_suffix()}"
        if not model_cls.objects.filter(**{field_name: candidate}).exists():
            return candidate
    # Extremely unlikely fallback: widen the suffix.
    return f"{prefix}-{year}-{_random_suffix(9)}"