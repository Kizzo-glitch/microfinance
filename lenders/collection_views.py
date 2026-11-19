"""
Lender pages for instant collection (see integrations/collection.py).

    enable  -> merchant code + C-Pay credentials, starts the M1.00 test payment
    otp     -> lender enters the code sent to their own phone
    resend  -> new test payment / new code
    disable -> stop instant collection on that account
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from integrations import collection
from integrations.models import CollectionSetup
from integrations.payments.gateway import (GatewayError, GatewayNotConfigured,
                                           supported_providers)
from micro.models import MobileMoneyAccount

PROFILE = "lenders:lender_profile"
TEST_OTP_SESSION_KEY = "collection_test_otp"


class EnableCollectionForm(forms.Form):
    mode = forms.ChoiceField(
        choices=CollectionSetup.MODE_CHOICES, initial="direct", widget=forms.RadioSelect,
        label="How should borrowers' payments reach you?")
    merchant_code = forms.CharField(
        max_length=64, label="Merchant code",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))
    client_code = forms.CharField(
        max_length=64, required=False, label="Client code",
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}))
    client_secret = forms.CharField(
        max_length=255, required=False, label="Client secret",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"},
                                   render_value=False))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("mode") == "direct":
            for f in ("client_code", "client_secret"):
                if not cleaned.get(f):
                    self.add_error(f, "Needed when you use your own merchant account.")
        return cleaned


class OtpForm(forms.Form):
    otp = forms.CharField(
        max_length=10, label="Code", widget=forms.TextInput(attrs={
            "class": "form-control form-control-lg", "inputmode": "numeric",
            "autocomplete": "one-time-code"}))


def _lender(request):
    return getattr(request.user, "lender", None)


def _own_setup(request, setup_id):
    return get_object_or_404(CollectionSetup, pk=setup_id, lender=_lender(request),
                             account__isnull=False)


def _gateway_error(request, exc):
    if isinstance(exc, GatewayNotConfigured):
        messages.info(request, "Instant collection isn't connected yet. Your manual payment "
                               "details keep working as before.")
    else:
        messages.error(request, str(exc))
    return redirect(PROFILE)


def collection_rows(lender):
    """(account, setup) for each of the lender's accounts that supports instant collection."""
    if lender is None:
        return []
    accounts = (MobileMoneyAccount.objects
                .filter(lender=lender, provider__in=supported_providers())
                .order_by("provider"))
    setups = {s.account_id: s for s in CollectionSetup.objects.filter(account__in=accounts)}
    return [(a, setups.get(a.pk)) for a in accounts]


@login_required
def enable(request, account_id):
    lender = _lender(request)
    account = get_object_or_404(MobileMoneyAccount, pk=account_id, lender=lender)
    if account.provider not in supported_providers():
        messages.error(request, "Instant collection isn't available for this provider yet.")
        return redirect(PROFILE)

    form = EnableCollectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            setup, test_otp = collection.enable(
                account, mode=d["mode"], merchant_code=d["merchant_code"].strip(),
                client_code=d["client_code"].strip(), client_secret=d["client_secret"])
        except GatewayError as exc:
            if isinstance(exc, GatewayNotConfigured):
                return _gateway_error(request, exc)
            form.add_error(None, str(exc))
        else:
            if setup.awaiting_otp:
                request.session[TEST_OTP_SESSION_KEY] = test_otp
                return redirect("lenders:collection_otp", setup_id=setup.pk)
            messages.error(request, setup.last_error or "Verification could not be started.")
            return redirect(PROFILE)

    return render(request, "collection/enable.html", {"form": form, "account": account})


@login_required
def otp(request, setup_id):
    setup = _own_setup(request, setup_id)
    if setup.is_verified:
        messages.success(request, "Instant collection is already on for this account.")
        return redirect(PROFILE)
    if not setup.awaiting_otp:
        messages.error(request, setup.last_error or "Please start verification again.")
        return redirect(PROFILE)

    form = OtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            setup = collection.confirm(setup, form.cleaned_data["otp"].strip())
        except GatewayError as exc:
            return _gateway_error(request, exc)
        request.session.pop(TEST_OTP_SESSION_KEY, None)
        if setup.is_verified:
            messages.success(request, f"Instant collection is on for {setup.account}. "
                                      "Borrowers' payments will be confirmed automatically.")
        else:
            messages.error(request, f"Verification failed: {setup.last_error or 'unknown reason'}. "
                                    "You can try again.")
        return redirect(PROFILE)

    return render(request, "collection/otp.html", {
        "form": form, "setup": setup,
        "test_otp": request.session.get(TEST_OTP_SESSION_KEY),
    })


@require_POST
@login_required
def resend(request, setup_id):
    setup = _own_setup(request, setup_id)
    try:
        setup, test_otp = collection.resend(setup)
    except GatewayError as exc:
        return _gateway_error(request, exc)
    if setup.awaiting_otp:
        request.session[TEST_OTP_SESSION_KEY] = test_otp
        messages.info(request, "A new code is on its way.")
        return redirect("lenders:collection_otp", setup_id=setup.pk)
    messages.error(request, setup.last_error or "Could not send a new code.")
    return redirect(PROFILE)


@require_POST
@login_required
def disable(request, setup_id):
    setup = _own_setup(request, setup_id)
    collection.disable(setup, reason="Turned off by the lender.")
    messages.success(request, "Instant collection is off for this account. "
                              "Borrowers can still pay you manually.")
    return redirect(PROFILE)
