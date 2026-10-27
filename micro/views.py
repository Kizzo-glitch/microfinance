from email.headerregistry import Group

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

#from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from .forms import UserRegistrationForm

from .models import User
from borrowers.models import BorrowerProfile
from lenders.models import LenderProfile

from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required

from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone


from loans.models import Loan
from groups.models import BorrowerGroup
from compliance.models import ComplianceProfile

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from loans.models import KeyFactsStatement




def landing(request):
	lenders_onboarded = LenderProfile.objects.all().count()
	
	verified_lenders = LenderProfile.objects.filter(
		verification_status__in=['verified', 'licensed']).count()

	borrowers_served = BorrowerProfile.objects.count()

	groups_registered = BorrowerGroup.objects.count()

	loans_total = (Loan.objects.aggregate(total=Sum('amount'))['total'] or Decimal("0.00"))

	submissions_filed = ComplianceProfile.objects.filter(current_stage='submitted').count()

	context = {
		"lenders_onboarded": f"{lenders_onboarded:,}",
		"verified_lenders": f"{verified_lenders:,}",
		"borrowers_served": f"{borrowers_served:,}",
		"groups_registered": f"{groups_registered:,}",
		"loans_disbursed_value": f"M {loans_total:,.2f}",
		"submissions_filed": f"{submissions_filed:,}",
		"uptime_pct": "99.9%",
		"as_of_date": timezone.now().strftime("%d %B %Y"),
	}

	return render(request, "landing.html", context)


def lender_compliance(request):	
	return render(request, 'lender_compliance.html', {})


def register(request):
	if request.method == 'POST':
		form = UserRegistrationForm(request.POST)
		if form.is_valid():
			form.save()
			
			username = form.cleaned_data['username']
			password = form.cleaned_data['password1']
			
			role = form.cleaned_data.get('role')

			user = authenticate(username=username, password=password)
			#login(request, user)
			
			# Redirect based on the role
			if role == 'lender':
				login(request, user)
				messages.success(request, f"Account created for {user.username} as a {role}!")
				return redirect('lenders:lender_profile')  # Redirect to lender info page
			elif role == 'borrower':
				login(request, user)
				messages.success(request, f"Account created for {user.username} as a {role}!")
				return redirect('borrowers:borrower_profile') 
			
			#return redirect('landing')  # Redirect to the login page
	else:
		form = UserRegistrationForm()
	return render(request, 'register.html', {'form': form})
	


class RegulatorPasswordChangeView(PasswordChangeView):
	template_name = 'password_setup.html'
	
	def get_success_url(self):
		# Redirect to the profile update page after success
		return reverse_lazy('regulator:regulator_profile')

	def form_valid(self, form):
		user = self.request.user
		user.must_change_password = False
		user.save()
		return super().form_valid(form)


def logout_user(request):
	logout(request)
	#messages.success(request, ('You have been logged out'))
	return redirect('landing') 




class CustomLoginView(LoginView):
	template_name = 'login.html'
	redirect_authenticated_user = True


@login_required
def role_based_redirect(request):
	if request.user.is_lender:
		return redirect('lenders:lender_index')  # To lender dashboard 
	elif request.user.is_borrower:
		return redirect('borrowers:borrower_index')  # To borrower dashboard 
	return redirect('landing')  # Default fallback





#++++++++++++++++++++++++++++++++++
# New kfs
#==================================
"""
KFS views — FINAL, against the real KeyFactsStatement (status-machine model
with on-model ack-record fields + record_borrower_ack / record_lender_ack).

The model methods enforce order and single-signing, so the view just:
  resolves the viewer -> calls the right record_* method -> notifies.
No field guessing left.
"""

@login_required
def view_kfs(request, kfs_id):
    #from loans.models import KeyFactsStatement
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)

    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    # Borrower-first ordering, read straight off the status machine.
    can_borrower_sign = role == "borrower" and kfs.status == "generated"
    can_lender_sign = role == "lender" and kfs.status == "borrower_ack"

    return render(request, "kfs_document.html", {
        "kfs": kfs,
        "snapshot": kfs.snapshot,
        "data": kfs.snapshot, 
        "loan": loan,
        "borrower": borrower,
        "lender": lender,
        "role": role,
        "can_borrower_sign": can_borrower_sign,
        "can_lender_sign": can_lender_sign,
        "fully_acknowledged": kfs.status == "acknowledged",
    })


@login_required
def acknowledge_kfs(request, kfs_id):
    if request.method != "POST":
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    from loans.models import KeyFactsStatement
    from .kfs_notifications import (
        notify_lender_of_borrower_ack, notify_borrower_fully_acknowledged,
    )

    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)
    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    typed_name = (request.POST.get("typed_name") or "").strip()
    if not typed_name:
        messages.error(request, "Please type your full name to acknowledge.")
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    if role == "borrower":
        ok = kfs.record_borrower_ack(user=request.user, typed_name=typed_name)
        if not ok:
            messages.info(request, "This statement can't be acknowledged again.")
        else:
            notify_lender_of_borrower_ack(loan, kfs)
            messages.success(request, "Thank you — your acknowledgement is recorded. "
                                      "The lender will confirm before disbursement.")
    else:  # lender
        ok = kfs.record_lender_ack(user=request.user, typed_name=typed_name)
        if not ok:
            # record_lender_ack returns False if borrower hasn't gone first,
            # or it's already confirmed/locked.
            if kfs.status == "generated":
                messages.error(request, "The borrower must acknowledge first.")
            else:
                messages.info(request, "This statement is already confirmed.")
        else:
            notify_borrower_fully_acknowledged(loan, kfs)
            messages.success(request, "Confirmed. Both parties have acknowledged "
                                      "the Key Facts Statement.")

    return redirect("loans:view_kfs", kfs_id=kfs_id)


def _viewer_role(user, borrower, lender):
    if getattr(borrower, "user", None) == user:
        return "borrower"
    if getattr(lender, "user", None) == user:
        return "lender"
    return None   # staff removed — only the actual parties sign (CBL-tight)



"""
KFS views — FINAL, against the real KeyFactsStatement (status-machine model
with on-model ack-record fields + record_borrower_ack / record_lender_ack).

The model methods enforce order and single-signing, so the view just:
  resolves the viewer -> calls the right record_* method -> notifies.
No field guessing left.
"""

@login_required
def view_kfs(request, kfs_id):
    from loans.models import KeyFactsStatement
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)

    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    # Borrower-first ordering, read straight off the status machine.
    can_borrower_sign = role == "borrower" and kfs.status == "generated"
    can_lender_sign = role == "lender" and kfs.status == "borrower_ack"

    print("KFS DEBUG — context keys going to template:", list({
    "kfs": kfs, "data": kfs.snapshot}.keys()))
    print("KFS DEBUG — data has provider?:", "provider" in (kfs.snapshot or {}))

    return render(request, "kfs_document.html", {
        "kfs": kfs,
        "snapshot": kfs.snapshot,
        "data": kfs.snapshot,
        "loan": loan,
        "borrower": borrower,
        "lender": lender,
        "role": role,
        "can_borrower_sign": can_borrower_sign,
        "can_lender_sign": can_lender_sign,
        "fully_acknowledged": kfs.status == "acknowledged",
    })



@login_required
def acknowledge_kfs(request, kfs_id):
    if request.method != "POST":
        return redirect("loans:view_kfs", kfs_id=kfs_id)


   
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)
    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("landing")

    typed_name = (request.POST.get("typed_name") or "").strip()
    if not typed_name:
        messages.error(request, "Please type your full name to acknowledge.")
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    if role == "borrower":
        ok = kfs.record_borrower_ack(user=request.user, typed_name=typed_name)
        if not ok:
            messages.info(request, "This statement can't be acknowledged again.")
        else:
            notify_lender_of_borrower_ack(loan, kfs)
            messages.success(request, "Thank you — your acknowledgement is recorded. "
                                      "The lender will confirm before disbursement.")
    else:  # lender
        ok = kfs.record_lender_ack(user=request.user, typed_name=typed_name)
        if not ok:
            # record_lender_ack returns False if borrower hasn't gone first,
            # or it's already confirmed/locked.
            if kfs.status == "generated":
                messages.error(request, "The borrower must acknowledge first.")
            else:
                messages.info(request, "This statement is already confirmed.")
        else:
            notify_borrower_fully_acknowledged(loan, kfs)
            messages.success(request, "Confirmed. Both parties have acknowledged "
                                      "the Key Facts Statement.")

    return redirect("loans:view_kfs", kfs_id=kfs_id)


def _viewer_role(user, borrower, lender):
    if getattr(borrower, "user", None) == user:
        return "borrower"
    if getattr(lender, "user", None) == user:
        return "lender"
    return None   # staff removed — only the actual parties sign (CBL-tight)




"""
KFS notifications — in-app + SMS + email, at each step of the acknowledgement flow.

Three triggers:
  1. KFS generated (on approval)         -> notify BORROWER to review & acknowledge
  2. Borrower acknowledged               -> notify LENDER to confirm
  3. Both acknowledged (lender confirmed)-> notify BORROWER it's complete

Reuses what you already have: Notification model, send_sms (honours
SMS_TEST_MODE), EmailMultiAlternatives. Each channel is wrapped so one failing
(e.g. no email on file) never blocks the others or the acknowledgement itself.
"""

def _kfs_url(request_or_none, kfs):
    """Absolute-ish path to the KFS view. Pass request to make it absolute."""
    path = reverse("loans:view_kfs", kwargs={"kfs_id": kfs.pk})
    return path  # templates/SMS can prefix with the site domain if needed.


# ── Trigger 1: KFS generated -> borrower, please review & acknowledge ──────

def notify_borrower_kfs_ready(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"Your Key Facts Statement for the M{loan.amount} loan from "
           f"{lender.company_name} is ready. Please review and acknowledge it "
           f"before the loan can be disbursed.")

    _in_app(borrower.user, msg, "kfs_ready", kfs.loan_application)
    _sms(borrower, "kfs_ready", {
        "name": borrower.full_name, "amount": loan.amount,
        "lender": lender.company_name, "ref": getattr(kfs, "reference", ""),
    })
    _email(borrower, "Your Key Facts Statement is ready", "emails/kfs_ready.html", {
        "borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs,
    })


# ── Trigger 2: borrower acknowledged -> lender, please confirm ─────────────

def notify_lender_of_borrower_ack(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{borrower.full_name} has acknowledged the Key Facts Statement for "
           f"their M{loan.amount} loan. Please confirm to proceed to disbursement.")

    _in_app(lender.user, msg, "kfs_borrower_acknowledged", kfs.loan_application)
    _sms(lender, "kfs_borrower_acknowledged", {
        "borrower": borrower.full_name, "amount": loan.amount,
        "ref": getattr(kfs, "reference", ""),
    })
    _email(lender, "Borrower acknowledged the Key Facts Statement",
           "emails/kfs_borrower_ack.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})


# ── Trigger 3: both acknowledged -> borrower, it's complete ────────────────

def notify_borrower_fully_acknowledged(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{lender.company_name} has confirmed your Key Facts Statement. "
           f"Both parties have now acknowledged it.")

    _in_app(borrower.user, msg, "kfs_complete", kfs.loan_application)
    _sms(borrower, "kfs_complete", {
        "name": borrower.full_name, "lender": lender.company_name,
        "ref": getattr(kfs, "reference", ""),
    })
    _email(borrower, "Key Facts Statement acknowledged by both parties",
           "emails/kfs_complete.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})


# ---------------------------------------------------------------------------
# channel helpers — each isolated so a failure can't block the others
# ---------------------------------------------------------------------------

def _in_app(user, message, category, loan_application=None):
    try:
        from borrowers.models import Notification        # (ADJUST import)
        Notification.objects.create(
            user=user, message=message, category=category,
            loan_application=loan_application,
        )
    except Exception:
        pass


def _sms(profile, template_key, context):
    try:
        from comms.sms import send_sms                    # (ADJUST import)
        phone = getattr(profile, "phone_number", None)
        if phone:
            send_sms(phone, template_key, context)         # honours SMS_TEST_MODE
    except Exception:
        pass


def _email(profile, subject, template, context):
    try:
        to = getattr(profile, "email_address", None) or getattr(
            getattr(profile, "user", None), "email", None)
        if not to:
            return
        body = render_to_string(template, context)
        email = EmailMultiAlternatives(subject, "", settings.EMAIL_HOST_USER, [to])
        email.attach_alternative(body, "text/html")
        email.send()
    except Exception:
        pass







"""
KFS views — wire the EXISTING kfs_document.html + KfsAcknowledgement model to
URLs, buttons, and notifications. Borrower-first, then lender-confirms.

Flow:
  loan approved -> generate_kfs() (already wired in on_loan_approved)
                -> notify borrower "review & acknowledge your Key Facts Statement"
  borrower opens view_kfs -> reads -> types name -> acknowledge_kfs (borrower)
                -> notify lender "borrower has acknowledged — please confirm"
  lender opens view_kfs -> confirms they've seen it -> acknowledge_kfs (lender)
                -> notify borrower "both parties acknowledged" + disbursement unlocks

HONESTY: only a VERIFIED typed-name acknowledgement counts. can_disburse()
(already built in Layer 5) stays the single gate — disbursement is blocked until
both parties have acknowledged. The snapshot the borrower signs is the frozen
one from generate_kfs(); re-reading never recomputes it.

(FIELD) marks = my best guess at KeyFactsStatement / KfsAcknowledgement field
names from the Layer 5 files. Correct them in THIS file to match.
"""
'''
@login_required
def view_kfs(request, kfs_id):
    """
    Show the Key Facts Statement to the borrower or lender, with the right
    acknowledgement action for whoever is viewing.
    """
    from loans.models import KeyFactsStatement         
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)

    loan = kfs.loan                                     
    borrower = loan.borrower
    lender = loan.lender

    # Who is this viewer, and are they allowed?
    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("home")

    # Acknowledgement state (from the two-party KfsAcknowledgement rows).
    borrower_ack = _ack_for(kfs, "borrower")             # (FIELD)
    lender_ack = _ack_for(kfs, "lender")

    # Can THIS viewer act now? Borrower-first ordering:
    #   borrower may acknowledge if they haven't yet.
    #   lender may confirm only AFTER the borrower has acknowledged.
    can_borrower_sign = role == "borrower" and borrower_ack is None
    can_lender_sign = (role == "lender"
                       and borrower_ack is not None
                       and lender_ack is None)

    return render(request, "loans/kfs_document.html", {
        "kfs": kfs,
        "snapshot": kfs.snapshot,                        # (FIELD) frozen JSON
        "loan": loan,
        "borrower": borrower,
        "lender": lender,
        "role": role,
        "borrower_ack": borrower_ack,
        "lender_ack": lender_ack,
        "can_borrower_sign": can_borrower_sign,
        "can_lender_sign": can_lender_sign,
        "fully_acknowledged": borrower_ack is not None and lender_ack is not None,
    })


@login_required
def acknowledge_kfs(request, kfs_id):
    """
    Record a typed-name acknowledgement for whoever is signing. POST only.
    Captures: who, typed name, when, and the KFS version/reference signed.
    """
    if request.method != "POST":
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    from loans.models import KeyFactsStatement, KfsAcknowledgement  # (ADJUST)
    kfs = get_object_or_404(KeyFactsStatement, pk=kfs_id)
    loan = kfs.loan
    borrower = loan.borrower
    lender = loan.lender

    role = _viewer_role(request.user, borrower, lender)
    if role is None:
        messages.error(request, "You don't have access to this document.")
        return redirect("home")

    typed_name = (request.POST.get("typed_name") or "").strip()
    if not typed_name:
        messages.error(request, "Please type your full name to acknowledge.")
        return redirect("loans:view_kfs", kfs_id=kfs_id)

    # Enforce borrower-first ordering + no double-signing.
    borrower_ack = _ack_for(kfs, "borrower")
    lender_ack = _ack_for(kfs, "lender")

    if role == "borrower":
        if borrower_ack is not None:
            messages.info(request, "You've already acknowledged this statement.")
            return redirect("loans:view_kfs", kfs_id=kfs_id)
    else:  # lender
        if borrower_ack is None:
            messages.error(request, "The borrower must acknowledge first.")
            return redirect("loans:view_kfs", kfs_id=kfs_id)
        if lender_ack is not None:
            messages.info(request, "You've already confirmed this statement.")
            return redirect("loans:view_kfs", kfs_id=kfs_id)

    # Record the acknowledgement (one row per party).
    KfsAcknowledgement.objects.create(
        kfs=kfs,                                         # (FIELD)
        party=role,                                      # (FIELD) 'borrower'|'lender'
        typed_name=typed_name,                           # (FIELD)
        acknowledged_by=request.user,                    # (FIELD)
        acknowledged_at=timezone.now(),                  # (FIELD)
        kfs_reference=getattr(kfs, "reference_number", ""),  # (FIELD) freeze what was signed
    )

    # --- notifications ---
    if role == "borrower":
        notify_lender_of_borrower_ack(loan, kfs)
        messages.success(request, "Thank you — your acknowledgement is recorded. "
                                  "The lender will confirm before disbursement.")
    else:
        notify_borrower_fully_acknowledged(loan, kfs)
        messages.success(request, "Confirmed. Both parties have acknowledged the "
                                  "Key Facts Statement.")

    return redirect("loans:view_kfs", kfs_id=kfs_id)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _viewer_role(user, borrower, lender):
    """Return 'borrower', 'lender', or None based on who's logged in."""
    # Adjust to your user<->profile relationships.
    if getattr(borrower, "user", None) == user:
        return "borrower"
    if getattr(lender, "user", None) == user:
        return "lender"
    if user.is_staff:
        return "lender"   # staff can act on the lender side; tighten if needed
    return None


def _ack_for(kfs, party):
    """The KfsAcknowledgement row for a party, or None."""
    return kfs.acknowledgements.filter(party=party).first()   # (FIELD related_name)
'''

'''
def _kfs_url(request_or_none, kfs):
    """Absolute-ish path to the KFS view. Pass request to make it absolute."""
    path = reverse("loans:view_kfs", kwargs={"kfs_id": kfs.pk})
    return path  # templates/SMS can prefix with the site domain if needed.


# ── Trigger 1: KFS generated -> borrower, please review & acknowledge ──────

def notify_borrower_kfs_ready(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"Your Key Facts Statement for the M{loan.amount} loan from "
           f"{lender.company_name} is ready. Please review and acknowledge it "
           f"before the loan can be disbursed.")

    _in_app(borrower.user, msg, "kfs_ready", loan)
    _sms(borrower, "kfs_ready", {
        "name": borrower.full_name, "amount": loan.amount,
        "lender": lender.company_name, "ref": getattr(kfs, "reference_number", ""),
    })
    _email(borrower, "Your Key Facts Statement is ready", "emails/kfs_ready.html", {
        "borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs,
    })


# ── Trigger 2: borrower acknowledged -> lender, please confirm ─────────────

def notify_lender_of_borrower_ack(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{borrower.full_name} has acknowledged the Key Facts Statement for "
           f"their M{loan.amount} loan. Please confirm to proceed to disbursement.")

    _in_app(lender.user, msg, "kfs_borrower_acknowledged", loan)
    _sms(lender, "kfs_borrower_acknowledged", {
        "borrower": borrower.full_name, "amount": loan.amount,
        "ref": getattr(kfs, "reference_number", ""),
    })
    _email(lender, "Borrower acknowledged the Key Facts Statement",
           "emails/kfs_borrower_ack.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})


# ── Trigger 3: both acknowledged -> borrower, it's complete ────────────────

def notify_borrower_fully_acknowledged(loan, kfs):
    borrower = loan.borrower
    lender = loan.lender
    msg = (f"{lender.company_name} has confirmed your Key Facts Statement. "
           f"Both parties have now acknowledged it.")

    _in_app(borrower.user, msg, "kfs_complete", loan)
    _sms(borrower, "kfs_complete", {
        "name": borrower.full_name, "lender": lender.company_name,
        "ref": getattr(kfs, "reference_number", ""),
    })
    _email(borrower, "Key Facts Statement acknowledged by both parties",
           "emails/kfs_complete.html",
           {"borrower": borrower, "lender": lender, "loan": loan, "kfs": kfs})


# ---------------------------------------------------------------------------
# channel helpers — each isolated so a failure can't block the others
# ---------------------------------------------------------------------------

def _in_app(user, message, category, loan):
    try:
        from borrowers.models import Notification        # (ADJUST import)
        Notification.objects.create(
            user=user, message=message, category=category,
            loan_application=getattr(loan, "application", None),  # (FIELD) if linked
        )
    except Exception:
        pass


def _sms(profile, template_key, context):
    try:
        from comms.sms import send_sms                    # (ADJUST import)
        phone = getattr(profile, "phone_number", None)
        if phone:
            send_sms(phone, template_key, context)         # honours SMS_TEST_MODE
    except Exception:
        pass


def _email(profile, subject, template, context):
    try:
        to = getattr(profile, "email_address", None) or getattr(
            getattr(profile, "user", None), "email", None)
        if not to:
            return
        body = render_to_string(template, context)
        email = EmailMultiAlternatives(subject, "", settings.EMAIL_HOST_USER, [to])
        email.attach_alternative(body, "text/html")
        email.send()
    except Exception:
        pass
'''