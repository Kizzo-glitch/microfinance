"""
Fedha-Grow — group credit profile (the lender bridge, Path A)
=============================================================
Turns a group's confirmed ledger into a creditworthiness signal a lender can
trust — WITHOUT the group taking on any liability. A member borrows individually
(existing flow); their group standing is surfaced as advisory context.

DESIGN — this is the extensible home for the deferred Path B:
  * Computed LIVE from confirmed data (no stale counters, always accurate).
  * `guarantee_capacity` is computed and DISPLAYED as context only — nothing
    acts on it. When Path B (group borrowing / co-signing) is built, it extends
    THIS object with liability logic; the shape is already here.

HONESTY:
  * Every figure is from CONFIRMED contributions / PAID payouts only — never
    claims. A lender lends real money on these numbers; they must be literally true.
  * Advisory, never a verdict. It informs the lender; it does not approve.

Path A adds NO liability: a member's group standing is a reference, and the
group is not a party to the member's loan.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from django.db import models
from django.utils import timezone


@dataclass
class MemberStanding:
    """One member's standing within a group — the core Path A signal."""
    member_name: str
    months_in_group: int
    confirmed_contribution_count: int
    confirmed_contribution_total: Decimal
    last_contribution_date: object = None
    # consistency % is intentionally omitted until a contribution SCHEDULE
    # exists (we're free-form for now). Placeholder kept for the seam.
    consistency_pct: float = None

    @property
    def summary(self) -> str:
        parts = [f"Member for {self.months_in_group} month(s)",
                 f"{self.confirmed_contribution_count} confirmed contribution(s)",
                 f"totalling M{self.confirmed_contribution_total:,.2f}"]
        return ", ".join(parts) + "."


@dataclass
class GroupCreditProfile:
    """
    A group's standing as a credit-relevant entity. Populated live.

    Path A uses: group_name/tenure/size/pool + a member's standing.
    Path B will extend: real guarantee/borrowing capacity + liability. The
    `guarantee_capacity` field below is DISPLAY-ONLY context today.
    """
    group_id: int
    group_name: str
    group_tenure_months: int
    active_member_count: int
    confirmed_pool_total: Decimal
    total_confirmed_contributions: Decimal
    # --- seam toward Path B: context only, NOTHING acts on this today ---
    guarantee_capacity: Decimal = Decimal("0.00")
    # the specific applicant's standing, when profiling for a loan application
    member_standing: MemberStanding = None
    computed_at: object = field(default_factory=timezone.now)

    @property
    def group_context_summary(self) -> str:
        return (f"{self.group_name}: {self.active_member_count} members, "
                f"{self.group_tenure_months}-month track record, "
                f"confirmed pool M{self.confirmed_pool_total:,.2f}.")


# =====================================================================
# Live computation from the ledger
# =====================================================================
def _months_between(start, end) -> int:
    if not start or not end:
        return 0
    return max((end.year - start.year) * 12 + (end.month - start.month), 0)


def build_group_credit_profile(group, *, for_membership=None) -> GroupCreditProfile:
    """
    Compute a group's credit profile live from CONFIRMED ledger data.
    If `for_membership` is given, include that member's individual standing.
    """
    from .models import GroupContribution
    from .group_pool import pool_balance, confirmed_contributions as _confirmed_total

    now = timezone.now()

    active = group.memberships.filter(status="active")
    tenure = _months_between(group.created_at, now)

    pool = pool_balance(group)
    total_confirmed = _confirmed_total(group)

    # --- guarantee capacity (DISPLAY-ONLY seam toward Path B) ---
    # A conservative notion of what the group *could* back: the current pool.
    # Nothing acts on this in Path A — it's context for the lender's eye.
    guarantee_capacity = pool if pool > 0 else Decimal("0.00")

    member_standing = None
    if for_membership is not None:
        mcontribs = group.contributions.filter(
            membership=for_membership, status="confirmed")
        agg = mcontribs.aggregate(
            total=models.Sum("amount"), count=models.Count("id"),
            last=models.Max("date_paid"))
        member_standing = MemberStanding(
            member_name=for_membership.borrower.full_name,
            months_in_group=_months_between(for_membership.joined_date, now),
            confirmed_contribution_count=agg["count"] or 0,
            confirmed_contribution_total=agg["total"] or Decimal("0.00"),
            last_contribution_date=agg["last"],
        )

    return GroupCreditProfile(
        group_id=group.id,
        group_name=group.name,
        group_tenure_months=tenure,
        active_member_count=active.count(),
        confirmed_pool_total=pool,
        total_confirmed_contributions=total_confirmed,
        guarantee_capacity=guarantee_capacity,
        member_standing=member_standing,
    )