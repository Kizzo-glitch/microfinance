
def is_group_admin(user, group):
    return group.admin == user.borrowerprofile

def is_sub_admin(user, group):
    return group.sub_admins.filter(id=user.borrowerprofile.id).exists()

def can_manage_operations(user, group):
    """Admin or sub-admin can manage day-to-day operations."""
    borrower = user.borrower
    return borrower == group.admin or group.sub_admins.filter(id=borrower.id).exists()
