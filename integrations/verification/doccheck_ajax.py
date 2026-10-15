"""
Layer 6b — AJAX endpoint for running checks on ONE document from the loan
application review screen, plus the approve-time acknowledgement guard.

Security: ownership is proven through the LOAN APPLICATION, not a standalone
per-document check. The lender must own the application the document belongs to
(request.user.lender), exactly as your LoanApplicationUpdateView already scopes.
So there's no separate permissive guard to get wrong.

Returns JSON so the review page can swap the result inline without reloading
and without disturbing the approve/reject form.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from loans.models import LoanApplication            
from borrowers.models import BorrowerDocs            
from integrations.services import run_document_checks  


@login_required
@require_POST
def run_doc_check_ajax(request, application_id, doc_id):
    """
    POST /applications/<application_id>/documents/<doc_id>/check/
    Runs checks on one document and returns its latest run as JSON.
    """
    lender = getattr(request.user, "lender", None)
    if lender is None:
        return HttpResponseForbidden("Lenders only.")

    # OWNERSHIP: the application must belong to THIS lender. This single filter
    # is the whole security guard — a lender can't reach another lender's
    # applicant's documents.
    application = get_object_or_404(
        LoanApplication, pk=application_id, lender=lender, is_deleted=False)

    # The document must belong to THIS application (direct FK). This is tighter
    # than a borrower-wide check: it scopes to documents uploaded for this
    # application, not everything the borrower ever uploaded.
    document = get_object_or_404(
        BorrowerDocs, pk=doc_id, loan_application=application)
    borrower = application.borrower

    # The engine cross-checks the statement against declared expenses + names.
    # These three lookups are the only place I'm guessing at YOUR BorrowerProfile
    # field names — adjust the (ADJUST) lines to your real attributes.
    run = run_document_checks(
        document,
        run_by=request.user,
        declared_expenses=_declared_expenses(borrower),   # (ADJUST) see helper
        profile_name=_borrower_name(borrower),            # (ADJUST) see helper
        id_name=_id_name(application),                    # (ADJUST) see helper
    )

    return JsonResponse({
        "ok": True,
        "doc_id": document.pk,
        "band": run.band,
        "band_display": run.get_band_display(),
        "band_tone": run.band_tone,
        "flag_count": run.flag_count,
        "inconclusive_count": run.inconclusive_count,
        "run_at": run.run_at.strftime("%d %b %Y %H:%M"),
        "flags": run.flags,              # list of {label, strength, detail, ...}
        "inconclusive": run.inconclusive,
    })


# ---------------------------------------------------------------------------
# Approve-time acknowledgement guard — call this inside your approval branch
# (LoanApplicationUpdateView.form_valid) BEFORE creating the Loan.
# ---------------------------------------------------------------------------

def unacknowledged_flags(application, request):
    """
    Returns True if this application has any document whose LATEST check run is
    'flagged' and the lender has NOT ticked the acknowledgement on this submit.

    The approve form includes a hidden/checkbox 'ack_doc_flags'. When the lender
    confirms the warning dialog, it's set to '1'. If there are flagged docs and
    it's not set, block and tell the template to show the warning.
    """
    if _has_flagged_documents(application):
        acked = request.POST.get("ack_doc_flags") == "1"
        return not acked
    return False


def _has_flagged_documents(application):
    # Documents are linked directly to the application (related_name='loan_documents').
    for d in application.loan_documents.all():
        latest = d.check_runs.first()      # newest via DocumentCheckRun.Meta.ordering
        if latest and latest.band == "flagged":
            return True
    return False


# ---------------------------------------------------------------------------
# Borrower-field resolvers — the ONLY guesses left. Adjust to BorrowerProfile.
# ---------------------------------------------------------------------------

def _declared_expenses(borrower):
    """
    The borrower's declared monthly expenses, used to check against observed
    spending on the statement. Point this at wherever you capture it (maybe on
    the affordability record, not the profile). Return 0 if you don't capture it
    — the expense-coverage check then reports 'unverified', which is honest.
    """
    return getattr(borrower, "declared_monthly_expenses", 0) or 0   # (ADJUST)


def _borrower_name(borrower):
    """
    The borrower's name, to cross-check against the statement's account holder.
    Your BorrowerProfile reaches the name via .user — adjust to the real fields
    (first_name/last_name, or a full_name property if you have one).
    """
    if borrower is None:
        return ""
    user = getattr(borrower, "user", None)
    if user is not None:
        full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        if full:
            return full
        return getattr(user, "username", "") or ""
    return getattr(borrower, "full_name", "") or ""                 # (ADJUST)


def _id_name(application):
    """
    The name as read from the borrower's ID document, if you store it. If you
    don't, return "" — the ID-name check then reports inconclusive (not a false
    fail). Wire this to wherever your OCR id-name capture lands.
    """
    return ""                                                        # (ADJUST)