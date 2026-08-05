from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .models import BorrowerGroup

def group_admin_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        borrower = getattr(request.user, "borrower", None)

        if borrower is None:
            messages.error(request, "Borrower profile not found.")
            return redirect("borrowers:borrower_index")

        if not BorrowerGroup.objects.filter(admin=borrower).exists():
            messages.error(
                request,
                "You do not have permission to access the Group Administrator area."
            )
            return redirect("groups:groups_landing")

        return view_func(request, *args, **kwargs)

    return wrapper
