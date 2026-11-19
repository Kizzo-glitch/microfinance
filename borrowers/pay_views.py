"""
Borrower "Pay now" pages (see integrations/repayments.py).

    pay     -> choose amount; instant (C-Pay) or manual with the lender's details
    otp     -> enter the code C-Pay sent to the borrower's phone
    result  -> paid / failed / being confirmed (refreshes itself)
    status  -> JSON for the result page's auto-refresh
    cancel  -> abandon a payment still waiting for its code
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from integrations import repayments
from integrations.models import GatewayCollection
from integrations.payments.gateway import GatewayError
from loans.models import Loan
from loans.schedule import amounts_due
from micro.models import MobileMoneyAccount

TEST_OTP_KEY = "pay_test_otp_{}"


def _own_collection(request, collection_id):
    return get_object_or_404(GatewayCollection, pk=collection_id,
                             loan__borrower__user=request.user)


@login_required
def pay(request, loan_id):
    loan = get_object_or_404(Loan, id=loan_id, borrower__user=request.user)
    active = repayments.active_collection(loan)
    if active is not None:
        messages.info(request, "You already have a payment in progress for this loan.")
        return redirect("borrowers:pay-result", collection_id=active.pk)

    if request.method == "POST":
        try:
            c, test_otp = repayments.start(loan, request.POST.get("option"))
        except repayments.PayNowError as exc:
            messages.error(request, str(exc))
            return redirect("borrowers:pay", loan_id=loan.id)
        except GatewayError as exc:
            messages.error(request, str(exc))
            return redirect("borrowers:pay", loan_id=loan.id)
        if test_otp:
            request.session[TEST_OTP_KEY.format(c.pk)] = test_otp
        if c.status == GatewayCollection.STATUS_AWAITING and c.required_action == "otp":
            return redirect("borrowers:pay-otp", collection_id=c.pk)
        return redirect("borrowers:pay-result", collection_id=c.pk)

    route, reason = repayments.instant_route(loan)
    lender = loan.lender
    return render(request, "pay/pay.html", {
        "loan": loan,
        "due": amounts_due(loan),
        "options": repayments.payment_options(loan),
        "instant": route,                 # (setup, borrower_account) or None
        "instant_reason": reason,
        "lender": lender,
        "lender_accounts": MobileMoneyAccount.objects.filter(lender=lender).order_by("provider"),
    })


@login_required
def otp(request, collection_id):
    c = _own_collection(request, collection_id)
    if c.otp_expired or c.status != GatewayCollection.STATUS_AWAITING:
        return redirect("borrowers:pay-result", collection_id=c.pk)
    if request.method == "POST":
        code = (request.POST.get("otp") or "").strip()
        if not code:
            messages.error(request, "Enter the code from your phone.")
        else:
            c = repayments.submit_otp(c, code)
            request.session.pop(TEST_OTP_KEY.format(c.pk), None)
            return redirect("borrowers:pay-result", collection_id=c.pk)
    return render(request, "pay/otp.html", {
        "c": c, "loan": c.loan,
        "test_otp": request.session.get(TEST_OTP_KEY.format(c.pk)),
    })


@login_required
def result(request, collection_id):
    c = repayments.refresh(_own_collection(request, collection_id))
    if c.status == GatewayCollection.STATUS_AWAITING and not c.otp_expired:
        return redirect("borrowers:pay-otp", collection_id=c.pk)
    return render(request, "pay/result.html", {"c": c, "loan": c.loan})


@login_required
def status(request, collection_id):
    c = repayments.refresh(_own_collection(request, collection_id))
    return JsonResponse({"status": c.status, "final": c.is_final})


@require_POST
@login_required
def cancel(request, collection_id):
    c = _own_collection(request, collection_id)
    # Only before the code is entered: without the code, no money can move.
    if c.status == GatewayCollection.STATUS_AWAITING:
        repayments._finish(c, GatewayCollection.STATUS_CANCELLED, "Cancelled by the borrower.")
        messages.info(request, "Payment cancelled. No money was taken.")
    return redirect("borrowers:loan-details", loan_id=c.loan_id)
