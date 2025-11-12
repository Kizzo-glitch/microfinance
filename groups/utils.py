from django.shortcuts import get_object_or_404
from borrowers.models import BorrowerProfile


def is_group_admin(user, group):
    try:
        return bool(user.borrower and group.admin_id == user.borrower.id)
    except Exception:
        return False


def is_sub_admin(user, group):
    try:
        return bool(user.borrower and group.sub_admins.filter(id=user.borrower.id).exists())
    except Exception:
        return False


def can_manage_operations(user, group):
    """Admin or sub-admin can manage operational tasks like invite/meetings."""
    return is_group_admin(user, group) or is_sub_admin(user, group)


def is_group_member(user, group):
    try:
        return bool(group.memberships.filter(borrower__user=user).exists() or group.memberships.filter(borrower=user.borrower).exists())
    except Exception:
        return False

"""
def is_group_admin(user, group):
    return group.admin == user.borrower

def is_sub_admin(user, group):
    return group.sub_admins.filter(id=user.borrower.id).exists()

def can_manage_operations(user, group):
    #Admin or sub-admin can manage day-to-day operations.
    borrower = user.borrower
    return borrower == group.admin or group.sub_admins.filter(id=borrower.id).exists()
"""