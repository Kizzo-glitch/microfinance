"""
Fedha-Grow — group permissions
===============================
Single source of truth for group authority: GroupMembership.role.

A person is always a BorrowerProfile (their borrower identity — own loans,
own dashboard). Group authority is layered on top via their membership role in
a specific group. The same person can be admin of one group, member of another.

Role tiers (least to most authority):
    probation < member < elder/secretary < treasurer < sub_admin < admin

Permission sets:
    MEMBER_ROLES  — anyone active in the group (can view)
    MONEY_ROLES   — can confirm contributions / handle money (treasurer up)
    STAFF_ROLES   — can do day-to-day management, e.g. add members (sub_admin up)
    ADMIN_ONLY    — reserved to the founder/admin: final approvals, sensitive
                    group changes, deleting things, changing constitution

The admin/sub_admin split is deliberate: sub_admins help run the group (invite,
add members) but FINAL approval and sensitive changes stay with the admin.
"""

from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from loans.models import Notification

from datetime import timedelta
from django.utils import timezone

from groups.models import GroupMembership


# ---- role sets ----
MEMBER_ROLES = {"admin", "sub_admin", "treasurer", "secretary", "elder", "member", "probation"}
MONEY_ROLES  = {"admin", "sub_admin", "treasurer"}
STAFF_ROLES  = {"admin", "sub_admin"}          # day-to-day management
ADMIN_ONLY   = {"admin"}                        # reserved to the founder/admin


# ---- core lookups ----
def group_membership(user, group):
    """The user's ACTIVE membership in this group, or None."""
    if not getattr(user, "is_authenticated", False):
        return None
    borrower = getattr(user, "borrower", None)
    if borrower is None:
        return None
    return group.memberships.filter(borrower=borrower, status="active").first()


def has_group_role(user, group, allowed_roles):
    """True if the user has an active membership whose role is in allowed_roles."""
    m = group_membership(user, group)
    return bool(m and m.role in allowed_roles)


# Convenience predicates (read naturally at call sites)
def is_group_member(user, group):  return has_group_role(user, group, MEMBER_ROLES)
def is_group_staff(user, group):   return has_group_role(user, group, STAFF_ROLES)
def is_group_admin(user, group):   return has_group_role(user, group, ADMIN_ONLY)
def can_handle_money(user, group): return has_group_role(user, group, MONEY_ROLES)


# ---- decorators for views that take a group id ----
def _resolve_group(kwargs):
    """Pull the group from common kwarg names used across the views."""
    from groups.models import BorrowerGroup
    gid = kwargs.get("group_id") or kwargs.get("pk") or kwargs.get("id")
    return get_object_or_404(BorrowerGroup, id=gid)


def _role_required(allowed_roles, denial_msg):
    """Factory: a decorator requiring one of allowed_roles in the group."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            group = _resolve_group(kwargs)
            if not has_group_role(request.user, group, allowed_roles):
                messages.error(request, denial_msg)
                return redirect("groups:group_detail", group.id)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# Ready-made decorators for group-scoped views (view must receive group_id/pk/id).
group_member_required = _role_required(
    MEMBER_ROLES, "You must be a member of this group to view that.")
group_staff_required = _role_required(
    STAFF_ROLES, "You need admin or sub-admin rights to do that.")
group_admin_only = _role_required(
    ADMIN_ONLY, "That action is reserved to the group administrator.")
money_role_required = _role_required(
    MONEY_ROLES, "Only the treasurer or an admin can handle group money.")

# ---- backwards-compatible: the "is this person an admin of ANY group" gate ----
# Your existing @group_admin_required guards the admin AREA (dashboard), which
# isn't tied to one group. Rewritten to use membership role instead of the
# BorrowerGroup.admin FK — so it now means "admin (or sub-admin) of at least one
# group" via the authoritative role, not the FK.
def group_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        borrower = getattr(request.user, "borrower", None)
        if borrower is None:
            messages.error(request, "Borrower profile not found.")
            return redirect("borrowers:borrower_index")

        has_staff_role = GroupMembership.objects.filter(
            borrower=borrower, status="active", role__in=STAFF_ROLES
        ).exists()

        if not has_staff_role:
            # Distinguish "brand-new admin, no group yet" from real rejection.
            if getattr(borrower, "is_group_admin", False):
                messages.info(request, "Create your first group to get started.")
                return redirect("groups:group_create")
            messages.error(request, "You do not have permission to access the Group Administrator area.")
            return redirect("groups:groups_landing")
        return view_func(request, *args, **kwargs)
    return wrapper

def group_admin_required2(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        borrower = getattr(request.user, "borrower", None)
        if borrower is None:
            messages.error(request, "Borrower profile not found.")
            return redirect("borrowers:borrower_index")

        is_any_group_staff = GroupMembership.objects.filter(
            borrower=borrower, status="active", role__in=STAFF_ROLES, role="admin"
        ).exists()
        if not is_any_group_staff:
            messages.error(request,
                "You do not have permission to access the Group Administrator area.")
            return redirect("groups:groups_landing")
        return view_func(request, *args, **kwargs)
    return wrapper


# =====================================================================
# Role elevation, acting roles, and deadlock avoidance
# =====================================================================
#
# Effective role respects expiry LIVE: an acting role whose acting_until has
# passed is treated as the previous_role immediately, without waiting for a
# cleanup job. A lazy tidy (revert_if_expired) persists that when convenient.


# How long an admin may be inactive (no login) before a sub_admin may claim
# acting-admin. Tunable.
ADMIN_ABSENCE_DAYS = 30
# When to start warning the admin they're going inactive.
ADMIN_WARNING_DAYS = 21


def effective_role(membership):
    """
    The role that actually applies right now. If an acting role has expired,
    the effective role is previous_role — even before any cleanup runs.
    """
    if membership is None:
        return None
    if membership.acting_until and membership.acting_until < timezone.now():
        return membership.previous_role or "member"
    return membership.role


def revert_if_expired(membership):
    """Persist an expired acting role back to previous_role. Safe to call anytime."""
    if (membership.acting_until and membership.acting_until < timezone.now()):
        membership.role = membership.previous_role or "member"
        membership.previous_role = None
        membership.acting_until = None
        membership.save(update_fields=["role", "previous_role", "acting_until"])
    return membership


def promote(membership, new_role, *, acting_until=None, previous_role=None, actor=None):
    """
    Elevate a membership. acting_until=None => permanent; a datetime => temporary
    (reverts to previous_role after it passes). Logs to ActivityLog.
    """
    from groups.models import ActivityLog
    if acting_until is not None and previous_role is None:
        previous_role = membership.role      # remember where to revert to
    membership.role = new_role
    membership.acting_until = acting_until
    membership.previous_role = previous_role
    membership.save(update_fields=["role", "acting_until", "previous_role"])

    kind = "acting" if acting_until else "permanent"
    ActivityLog.objects.create(
        group=membership.group,
        actor=getattr(actor, "user", None) if actor else None,
        action="role_changed",
        details=f"{membership.borrower.full_name} -> {new_role} ({kind}"
                + (f", until {acting_until:%d %b %Y}" if acting_until else "") + ")",
    )
    return membership


# ---- deadlock avoidance ----
def admin_is_absent(group, days=ADMIN_ABSENCE_DAYS):
    """
    True if no active admin of the group has logged in within `days`.
    Uses User.last_login as the (coarse, zero-cost) signal.
    """
    cutoff = timezone.now() - timedelta(days=days)
    admins = group.memberships.filter(status="active", role="admin")
    for m in admins:
        user = getattr(m.borrower, "user", None)
        last = getattr(user, "last_login", None) if user else None
        if last and last >= cutoff:
            return False      # an admin is active -> not absent
    # absent if there are admins but none recently active, OR no admin at all
    return True


def can_claim_acting_admin(user, group):
    """
    A sub_admin may claim acting-admin ONLY when the admin has been absent
    >= ADMIN_ABSENCE_DAYS. This is the deadlock escape — a capability that
    unlocks on demonstrable absence, not an automatic transfer.
    """
    m = group_membership(user, group)
    if not m or effective_role(m) != "sub_admin":
        return False
    return admin_is_absent(group)


def claim_acting_admin(user, group):
    """
    A sub_admin explicitly claims acting-admin. Returns (ok, message).
    Deliberate action, logged, and the absent admin is notified.
    """
    if not can_claim_acting_admin(user, group):
        return False, "You can only step in once the admin has been inactive for the required period."
    m = group_membership(user, group)
    # acting admin for 30 days, revert to sub_admin after (renewable if still absent)
    promote(m, "admin",
            acting_until=timezone.now() + timedelta(days=ADMIN_ABSENCE_DAYS),
            previous_role="sub_admin", actor=m.borrower)
    _notify_admin_of_takeover(group, m)
    return True, "You are now acting admin. The group administrator has been notified."


def _notify_admin_of_takeover(group, acting_membership):
    """Tell the (absent) original admin someone has stepped in."""
    for m in group.memberships.filter(status="active", role="admin"):
        user = getattr(m.borrower, "user", None)
        if not user:
            continue
        Notification.objects.create(
            user=user,
            category="group_update",
            message=(f"{acting_membership.borrower.full_name} has become acting admin of "
                     f"{group.name} due to 30 days of inactivity. Log in to resume your role."),
        )
        # SMS too — an absent admin likely isn't in the app.
        # send_sms(m.borrower.phone_number, "acting_admin_appointed",
        #          {"name": m.borrower.full_name, "actor": acting_membership.borrower.full_name,
        #           "group": group.name})


def check_admin_inactivity(group):
    """
    Reusable callable — the detection + warning logic. Called LAZILY today
    (on group page visits by any member); a scheduled job can call the SAME
    function later with no change. Fires a one-time warning as the admin nears
    the absence threshold.
    """
    cutoff_warn = timezone.now() - timedelta(days=ADMIN_WARNING_DAYS)
    cutoff_absent = timezone.now() - timedelta(days=ADMIN_ABSENCE_DAYS)

    for m in group.memberships.filter(status="active", role="admin"):
        user = getattr(m.borrower, "user", None)
        last = getattr(user, "last_login", None) if user else None
        if not user or not last:
            continue
        # In the warning window (past warn threshold, not yet fully absent).
        if cutoff_absent < last <= cutoff_warn:
            already = Notification.objects.filter(
                user=user, category="group_update",
                message__icontains="inactive in", ).exists()
            if not already:
                Notification.objects.create(
                    user=user, category="group_update",
                    message=(f"You've been inactive in {group.name} for several weeks. "
                             f"Appoint an acting admin or log in — after 30 days inactivity a "
                             f"sub-admin may temporarily step in."),
                )
                # send_sms(m.borrower.phone_number, "admin_inactivity_warning",
                #          {"name": m.borrower.full_name, "group": group.name})