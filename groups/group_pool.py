"""
Fedha-Grow — group pool balance
===============================
Pool = confirmed contributions - confirmed (paid) payouts.

A payout debits the pool; a contribution credits it. Both count only when
confirmed/paid, never on claim — so the pool always reflects money that
genuinely moved. Keep this the single source of truth for "what's in the pool".
"""

from decimal import Decimal
from django.db import models

from .models import GroupContribution, GroupPayout


def confirmed_contributions(group) -> Decimal:
    return group.contributions.filter(status="confirmed").aggregate(
        t=models.Sum("amount"))["t"] or Decimal("0.00")


def paid_payouts(group) -> Decimal:
    return group.payouts.filter(status="paid").aggregate(
        t=models.Sum("amount"))["t"] or Decimal("0.00")


def pool_balance(group) -> Decimal:
    """Money currently available in the group pool."""
    return confirmed_contributions(group) - paid_payouts(group)