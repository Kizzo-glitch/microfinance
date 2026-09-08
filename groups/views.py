
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from django.db.models import Q

from django.views.decorators.http import require_POST

from borrowers.models import BorrowerProfile
from borrowers.forms import BorrowerProfileForm
from loans.models import Loan, Notification
from .models import (
    BorrowerGroup, GroupMembership, GroupConstitution, GroupInvitation,
    GroupJoinRequest, GroupDocument, ActivityLog,GroupFinancialRules,
    GroupContribution, GroupPayout, DataProcessingConsent,
)
from .forms import (
    BorrowerGroupRegistrationForm, BorrowerGroupForm, GroupAdminReviewForm,
    GroupConstitutionForm, GroupContributionClaimForm, GroupInvitationForm, BorrowerMiniForm, ActivationForm,
    GroupFinancialRulesForm, GroupMeetingForm,
)
from .group_permissions import (
    STAFF_ROLES, group_admin_required, group_member_required, group_staff_required,
    group_admin_only, is_group_staff, is_group_admin, group_membership,
    check_admin_inactivity, claim_acting_admin, can_claim_acting_admin, promote, 
    can_handle_money, effective_role, ADMIN_ABSENCE_DAYS, admin_is_absent,
)


from comms.sms.service import send_sms
from .group_pool import pool_balance
from .consent_statements import get_statement, CURRENT_VERSION
from .member_import_core import parse_workbook, classify_rows, EXPECTED_COLUMNS, REQUIRED_COLUMNS

from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill
from django.http import HttpResponse
 

User = get_user_model()


# =====================================================================
# Landing / auth / profile
# =====================================================================
def group_landing(request):
    return render(request, 'group_landing.html')


def register_group_admin(request):
    if request.method == "POST":
        form = BorrowerGroupRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'borrower'
            user.save()
            login(request, user)
            messages.success(request, "Account created. Please complete your profile before creating a group.")
            return redirect('groups:group_borrower_profile')
    else:
        form = BorrowerGroupRegistrationForm()
    return render(request, 'register_group_admin.html', {'form': form})


@login_required
def group_borrower_profile(request):
    """
    A group admin is a full borrower. This completes their BorrowerProfile.
    (Single canonical version — the old _profile2 twin is removed.)
    """
    user = request.user
    if not getattr(user, 'is_borrower', False):
        messages.error(request, "You must be logged in as a borrower to access that page.")
        return redirect('groups:groups_landing')

    profile, _ = BorrowerProfile.objects.get_or_create(user=user)
    if not profile.is_group_admin:
        profile.is_group_admin = True
        profile.save(update_fields=["is_group_admin"])

    if request.method == 'POST':
        form = BorrowerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.user = user
            updated.save()
            messages.success(request, "Your info has been updated.")
            return redirect('groups:group_admin_dashboard')
    else:
        form = BorrowerProfileForm(instance=profile, initial={
            'phone_number': getattr(user, 'phone_number', ''),
            'email_address': user.email,
            'full_name': f"{user.first_name} {user.last_name}".strip(),
        })

    outstanding_loans = Loan.objects.filter(borrower=profile, outstanding_balance__gt=0).count()
    overdue_loans = Loan.objects.filter(borrower=profile, due_date__lt=date.today(), outstanding_balance__gt=0).count()
    total_debt = Loan.objects.filter(borrower=profile).aggregate(total=Sum('outstanding_balance'))['total'] or 0

    return render(request, "group_borrower_profile.html", {
        'form': form, 'outstanding_loans': outstanding_loans,
        'overdue_loans': overdue_loans, 'total_debt': total_debt,
    })



def group_admin_login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.error(request, "Invalid login credentials.")
            return render(request, "login_group_admin.html")

        borrower = getattr(user, "borrower", None)
        is_group_staff = bool(borrower) and GroupMembership.objects.filter(
            borrower=borrower, status="active", role__in=STAFF_ROLES
        ).exists()

        if is_group_staff:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "Welcome to your Group dashboard.")
            return redirect("groups:group_admin_dashboard")

        messages.error(request, "You don't have admin or sub-admin access to any group.")
        return render(request, "login_group_admin.html")

    return render(request, "login_group_admin.html")


def group_admin_login2(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST["username"], password=request.POST["password"])
        if user is not None:
            profile = BorrowerProfile.objects.filter(user=user).first()
            if profile and profile.is_group_admin:
                login(request, user)
                messages.success(request, "Welcome to your Group Admin Dashboard.")
                return redirect("groups:group_admin_dashboard")
            messages.error(request, "You are not authorized as a Group Admin.")
        else:
            messages.error(request, "Invalid login credentials.")
    return render(request, "login_group_admin.html")




def admin_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('groups:groups_landing')


# =====================================================================
# Admin dashboard
# =====================================================================
@login_required
@group_admin_required
def group_admin_dashboard(request):
    borrower = getattr(request.user, 'borrower', None)

    # Groups where this borrower holds an admin/sub_admin role (authority),
    # not merely the owner FK.
    staff_memberships = GroupMembership.objects.filter(
        borrower=borrower, status="active", role__in=["admin", "sub_admin"]
    ).values_list("group_id", flat=True)
    administered_groups = BorrowerGroup.objects.filter(id__in=staff_memberships).order_by('-created_at')
    group_ids = list(administered_groups.values_list('id', flat=True))

    # Lazy inactivity check — fires admin warnings without a scheduler.
    for g in administered_groups:
        check_admin_inactivity(g)

    memberships = GroupMembership.objects.filter(group_id__in=group_ids, status="active")
    pending_requests = GroupJoinRequest.objects.filter(group_id__in=group_ids, status='pending').order_by('-requested_at')
    pending_invitations = GroupInvitation.objects.filter(group_id__in=group_ids, status='pending').order_by('-sent_at')

    context = {
        'administered_groups': administered_groups,
        'total_groups': administered_groups.count(),
        'total_members': memberships.count(),
        'pending_count': pending_requests.count(),
        'pending_invitations_count': pending_invitations.count(),
        'recent_join_requests': pending_requests[:8],
        'recent_invitations': pending_invitations[:8],
    }
    return render(request, 'group_admin_dashboard.html', context)


# =====================================================================
# Group CRUD
# =====================================================================
@login_required
def group_list(request):
    borrower = request.user.borrower
    groups = (BorrowerGroup.objects.filter(memberships__borrower=borrower)
              .distinct().order_by('-created_at'))
    return render(request, 'group_list.html', {'groups': groups})


@login_required
def group_create(request):
    borrower = request.user.borrower
    if request.method == 'POST':
        form = BorrowerGroupForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.save(commit=False)
            group.admin = borrower          # owner/founder provenance
            group.status = 'draft'
            group.save()
            # Authority: the creator's admin-role membership.
            GroupMembership.objects.create(
                group=group, borrower=borrower, role='admin',
                status='active', verification_status='fully_verified')
            ActivityLog.objects.create(
                group=group, actor=request.user, action="group_created",
                details=f"Group '{group.name}' created.")
            messages.success(request, "Group created. You can now add the constitution and rules.")
            return redirect('groups:group_detail', group.id)
    else:
        form = BorrowerGroupForm()
    return render(request, 'group_create.html', {'form': form})


@login_required
@group_member_required
def group_detail(request, pk):
    group = get_object_or_404(BorrowerGroup, pk=pk)
    rules = getattr(group, 'financial_rules', None)
    can_edit = is_group_admin(request.user, group)   

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, "Only the group administrator can edit the rules.")
            return redirect('groups:group_detail', pk=group.pk)
        form = GroupFinancialRulesForm(request.POST, instance=rules)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.group = group
            obj.save()
            messages.success(request, "Group financial rules updated.")
            return redirect('groups:group_detail', pk=group.pk)
    else:
        form = GroupFinancialRulesForm(instance=rules)

    return render(request, 'group_detail.html', {
        'group': group, 'form': form, 'can_edit': can_edit,
        'financial_rules': rules,
        'join_requests': group.join_requests.all(),
        'pending_requests_count': group.join_requests.filter(status='pending').count(),

		'is_admin': is_group_admin(request.user, group),
		'can_manage': is_group_staff(request.user, group),
		'active_member_count': group.memberships.filter(status='active').count(),
        'can_handle_money': can_handle_money(request.user, group),
		'pending_contributions_count': group.contributions.filter(status='claimed').count(),
    })

# views.py
@login_required
@group_admin_only
def group_financial_rules(request, group_id):
    """Dedicated page for setting up a group's contribution + payout rules."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    rules, _ = GroupFinancialRules.objects.get_or_create(group=group)
    if request.method == 'POST':
        form = GroupFinancialRulesForm(request.POST, instance=rules)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(
                group=group, actor=request.user,
                action="group_updated", details="Financial rules updated.")
            messages.success(request, "Financial rules saved.")
            return redirect('groups:group_detail', group.id)
    else:
        form = GroupFinancialRulesForm(instance=rules)
    return render(request, 'group_financial_rules.html', {'group': group, 'form': form})



@login_required
@group_admin_only
def group_edit(request, pk):
    group = get_object_or_404(BorrowerGroup, pk=pk)
    if request.method == 'POST':
        form = BorrowerGroupForm(request.POST, request.FILES, instance=group)
        if form.is_valid():
            form.save()
            ActivityLog.objects.create(group=group, actor=request.user,
                                       action="group_updated", details="Group details updated.")
            messages.success(request, "Group details updated.")
            return redirect('groups:group_detail', group.id)
    else:
        form = BorrowerGroupForm(instance=group)
    return render(request, 'group_edit.html', {'form': form, 'group': group})


@login_required
@group_admin_only
def group_constitution(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    constitution, _ = GroupConstitution.objects.get_or_create(group=group)
    if request.method == 'POST':
        form = GroupConstitutionForm(request.POST, instance=constitution)
        if form.is_valid():
            form.save()
            messages.success(request, "Constitution saved.")
            return redirect('groups:group_detail', group.id)
    else:
        form = GroupConstitutionForm(instance=constitution)
    return render(request, 'group_constitution.html', {'group': group, 'form': form})


# =====================================================================
# Members
# =====================================================================
@login_required
@group_member_required
def group_members(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    members = GroupMembership.objects.filter(group=group).select_related('borrower')
    return render(request, 'group_members.html', {'group': group, 'members': members})



# not this dropdown — you don't casually "set someone to admin")
ASSIGNABLE_ROLES = {"member", "sub_admin", "treasurer", "secretary", "elder"}
 
 
@login_required
@group_staff_required
def manage_members(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    members = group.memberships.select_related("borrower__user")
 
    if request.method == "POST":
        # role changes / removal are ADMIN-ONLY, even though sub_admins can view
        if not is_group_admin(request.user, group):
            messages.error(request, "Only the group administrator can change roles or remove members.")
            return redirect("groups:manage_members", group_id=group.id)
 
        target = get_object_or_404(GroupMembership, id=request.POST.get("member_id"), group=group)
        action = request.POST.get("action")
 
        # never let an admin act on themselves or on another admin here
        if target.borrower == request.user.borrower or target.role == "admin":
            messages.error(request, "That member can't be changed here.")
            return redirect("groups:manage_members", group_id=group.id)
 
        if action == "set_role":
            new_role = request.POST.get("new_role")
            if new_role not in ASSIGNABLE_ROLES:
                messages.error(request, "Invalid role.")
            elif new_role == target.role:
                messages.info(request, f"{target.borrower.full_name} is already {target.get_role_display()}.")
            else:
                promote(target, new_role, actor=request.user.borrower)   # logged
                messages.success(request, f"{target.borrower.full_name} is now {target.get_role_display()}.")
 
        elif action == "remove":
            ActivityLog.objects.create(
                group=group, actor=request.user, action="member_removed",
                details=f"{target.borrower.full_name} removed.")
            target.delete()
            messages.warning(request, f"{target.borrower.full_name} removed from the group.")
 
        else:
            messages.error(request, "Unknown action.")
 
        return redirect("groups:manage_members", group_id=group.id)
 
    return render(request, "manage_members.html", {
        "group": group,
        "members": members,
        "is_admin": is_group_admin(request.user, group),
    })


@login_required
@group_member_required
def roles_and_succession(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
 
    active = group.memberships.filter(status="active").select_related("borrower")
 
    leadership = {
        "admins":     active.filter(role="admin"),
        "sub_admins": active.filter(role="sub_admin"),
        "treasurers": active.filter(role="treasurer"),
        "secretaries": active.filter(role="secretary"),
        "elders":     active.filter(role="elder"),
    }
 
    return render(request, "roles_and_succession.html", {
        "group": group,
        "leadership": leadership,
        "is_admin": is_group_admin(request.user, group),
        "admin_absent": admin_is_absent(group),
        "absence_days": ADMIN_ABSENCE_DAYS,
        # can the CURRENT viewer step up as acting admin? (sub_admin + admin absent)
        "can_claim_acting": can_claim_acting_admin(request.user, group),
    })

'''
@login_required
@group_staff_required
def manage_members2(request, group_id):
    """Staff (admin + sub_admin) can view/manage; role CHANGES are admin-only."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    members = group.memberships.select_related('borrower__user')

    if request.method == "POST":
        action = request.POST.get('action')
        target = get_object_or_404(GroupMembership, id=request.POST.get('member_id'), group=group)

        # Promote / demote / remove are ADMIN-ONLY (reserved), even though
        # sub_admins can reach this page to view members.
        if action in {"promote", "demote", "remove"} and not is_group_admin(request.user, group):
            messages.error(request, "Only the group administrator can change roles or remove members.")
            return redirect('groups:manage_members', group_id=group.id)

        if action == "promote" and target.role == "member":
            promote(target, "sub_admin", actor=request.user.borrower)
            messages.success(request, f"{target.borrower.full_name} promoted to Sub-Admin.")
        elif action == "demote" and target.role == "sub_admin":
            promote(target, "member", actor=request.user.borrower)
            messages.info(request, f"{target.borrower.full_name} demoted to Member.")
        elif action == "remove":
            ActivityLog.objects.create(group=group, actor=request.user, action="member_removed",
                                       details=f"{target.borrower.full_name} removed.")
            target.delete()
            messages.warning(request, f"{target.borrower.full_name} removed from the group.")
        else:
            messages.error(request, "Invalid action or role change not allowed.")
        return redirect('groups:manage_members', group_id=group.id)

    return render(request, 'manage_members.html', {
        'group': group, 'members': members,
        'is_admin': is_group_admin(request.user, group),
    })


@login_required
@group_admin_only
def manage_sub_admins(request, group_id):
    """Kept for compatibility. Sub-admin status is now the membership role;
    this simply promotes/demotes via role, not the old M2M."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    members = group.memberships.select_related('borrower').all()
    if request.method == 'POST':
        selected = set(request.POST.getlist('sub_admins'))
        for m in members:
            if str(m.id) in selected and m.role == 'member':
                promote(m, 'sub_admin', actor=request.user.borrower)
            elif str(m.id) not in selected and m.role == 'sub_admin':
                promote(m, 'member', actor=request.user.borrower)
        messages.success(request, "Sub-admins updated.")
        return redirect('groups:group_detail', group.id)
    return render(request, 'manage_sub_admins.html', {
        'group': group, 'members': members,
        'current_sub_admins': members.filter(role='sub_admin'),
    })
'''

@login_required
def claim_acting_admin_view(request, group_id):
    """A sub_admin explicitly steps up when the admin is absent (deadlock escape)."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if request.method == 'POST':
        ok, msg = claim_acting_admin(request.user, group)
        (messages.success if ok else messages.error)(request, msg)
    return redirect('groups:group_detail', group.id)


# =====================================================================
# Activity log & documents
# =====================================================================
@login_required
@group_member_required
def group_activity_log(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    logs = group.activity_logs.all()
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    return render(request, 'activity_log.html', {'group': group, 'logs': logs})


@login_required
@group_staff_required
def group_documents(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if request.method == 'POST':
        file = request.FILES.get('file')
        if file:
            version = group.documents.filter(file__icontains=file.name).count() + 1
            GroupDocument.objects.create(
                group=group, uploaded_by=request.user.borrower, file=file,
                version=version, description=request.POST.get('description', ''))
            ActivityLog.objects.create(group=group, actor=request.user,
                                       action="document_uploaded", details=file.name)
            messages.success(request, "Document uploaded.")
            return redirect('groups:group_documents', group.id)
    return render(request, 'group_documents.html',
                  {'group': group, 'documents': group.documents.all()})


# =====================================================================
# Invitations  (staff may invite; SMS via catalogue TODO)
# =====================================================================
@login_required
@group_staff_required
def send_group_invite(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    inviter = request.user.borrower

    if request.method == 'POST':
        form = GroupInvitationForm(request.POST)
        profile_form = BorrowerMiniForm(request.POST)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.group = group
            invitation.invited_by = inviter

            phone = request.POST.get('invitee_phone')
            email = request.POST.get('invitee_email')
            existing = BorrowerProfile.objects.filter(
                models.Q(phone_number=phone) | models.Q(user__email=email)).first()

            if existing and existing.user:
                messages.warning(request, f"{existing.full_name} already has an account and cannot be re-invited.")
                return redirect('groups:group_detail', group.id)
            if existing:
                borrower = existing
            elif profile_form.is_valid():
                borrower = profile_form.save()
            else:
                messages.error(request, "Please complete the invitee profile correctly.")
                return render(request, 'send_group_invite.html',
                              {'group': group, 'form': form, 'profile_form': profile_form})

            invitation.invitee = borrower
            invitation.invitee_name = borrower.full_name
            invitation.invitee_phone = borrower.phone_number
            invitation.invitee_email = (borrower.user.email if borrower.user else email)
            invitation.save()

            activation_url = request.build_absolute_uri(invitation.get_activation_url())
            send_sms(invitation.invitee_phone, "group_invitation",
                     {"name": invitation.invitee_name, "group": group.name,
                     "code": invitation.invitation_code, "url": activation_url})
            invitation.sms_sent = True
            invitation.sms_sent_at = timezone.now()
            invitation.save()

            messages.success(request, f"Invitation sent. Code: {invitation.invitation_code}")
            return redirect('groups:group_detail', group.id)
        messages.error(request, "Please correct the errors below.")
    else:
        form = GroupInvitationForm()
        profile_form = BorrowerMiniForm()
    return render(request, 'send_group_invite.html',
                  {'group': group, 'form': form, 'profile_form': profile_form})


@login_required
def borrower_search(request):
    q = (request.GET.get("q") or "").strip()
    group_id = request.GET.get("group_id")
 
    if len(q) < 2:
        return JsonResponse({"results": []})   # require at least 2 chars
 
    matches = BorrowerProfile.objects.filter(
        Q(full_name__icontains=q) | Q(phone_number__icontains=q)
    ).select_related("user")[:10]   # cap results
 
    # which of these are already active members of this group?
    group_member_ids = set()
    if group_id:
        group = BorrowerGroup.objects.filter(id=group_id).first()
        if group:
            group_member_ids = set(
                group.memberships.filter(status="active")
                .values_list("borrower_id", flat=True))
 
    results = []
    for b in matches:
        phone = b.phone_number or ""
        results.append({
            "id": b.id,
            "name": b.full_name,
            # show only the tail of the phone in the picker (privacy)
            "phone_tail": ("…" + phone[-4:]) if len(phone) >= 4 else phone,
            "phone": phone,                       # full phone, to fill the field on pick
            "email": (b.user.email if b.user else ""),
            "has_account": bool(b.user_id),        # already registered
            "in_this_group": b.id in group_member_ids,
        })
    return JsonResponse({"results": results})


def activate_invite(request, code=None):
    """Public — invitee may not have an account yet."""
    invitation_code = (code or request.POST.get('invitation_code') or '').strip().upper()
    if not invitation_code:
        messages.error(request, "Missing invitation code.")
        return render(request, "activate_invite.html",
                      {'form': ActivationForm(), 'show_code_entry': True})

    invite = get_object_or_404(GroupInvitation, invitation_code=invitation_code, status='pending')
    borrower_profile = invite.invitee

    # Split the captured name only as a FALLBACK to pre-fill the form; the
    # person can correct it, and their correction wins (see below).
    parts = (invite.invitee_name or "").split()
    default_first = parts[0] if parts else ""
    default_last = parts[-1] if len(parts) > 1 else ""

    if request.method == "POST":
        form = ActivationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            email = form.cleaned_data.get('email') or invite.invitee_email
            phone = form.cleaned_data.get('phone_number') or invite.invitee_phone
            # The person's OWN confirmation of their name wins over the split.
            first_name = form.cleaned_data.get('first_name') or default_first
            last_name = form.cleaned_data.get('last_name') or default_last

            if borrower_profile.user:
                user = borrower_profile.user
                user.username, user.email = username, email
                user.first_name, user.last_name = first_name, last_name
                if not getattr(user, "role", ""):
                    user.role = 'borrower'                 # set role if missing
                if hasattr(user, "phone_number"):
                    user.phone_number = phone
                user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                    first_name=first_name, last_name=last_name)
                user.role = 'borrower'                     # <-- the fix: set role
                if hasattr(user, "phone_number"):
                    user.phone_number = phone
                user.save()
                borrower_profile.user = user
                borrower_profile.save()

            # Record the person's DIGITAL consent (their own act, no agent).
            _record_consent(borrower_profile, method="digital", given=True)

            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save()

            GroupMembership.objects.get_or_create(
                group=invite.group, borrower=borrower_profile,
                defaults={"role": "member", "status": "active",
                          "verification_status": "identity_verified",
                          "joined_date": timezone.now()})

            # Custom user model with a non-default auth backend can make login()
            # ambiguous — be explicit about the backend to avoid a ValueError.
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f"Welcome {borrower_profile.full_name}, your account is now active.")
            return redirect("borrowers:borrower_index")
    else:
        form = ActivationForm(initial={
            'email': invite.invitee_email,
            'phone_number': invite.invitee_phone,
            'first_name': default_first,
            'last_name': default_last,
        })

    from groups.consent_statements import get_statement
    return render(request, "activate_invite.html", {
        "form": form,
        "invite": invite,
        "borrower_profile": borrower_profile,
        "consent_statement": get_statement(),
    })

"""
Fedha-Grow — consent views (capture + printable)
================================================
  * consent_blank_form   — printable blank form for a person to sign before
                           an agent captures their profile.
  * consent_record       — printable record of a specific person's captured
                           consent (proof of what they agreed to, when, by whom).
  * capture flow is handled where the agent creates/edits the profile (see
    _record_consent helper), not a standalone view.
"""
def _record_consent(borrower, *, method, captured_by=None, signed_form=None,
                    witness_name="", given=True):
    """
    Create a consent record. Call this from the profile-capture / activation
    flow — e.g. after an agent captures a profile from a signed physical form,
    or after a person ticks consent when activating their account.
    """
    return DataProcessingConsent.objects.create(
        borrower=borrower,
        statement_version=CURRENT_VERSION,
        given=given,
        method=method,
        captured_by=captured_by,
        signed_form=signed_form,
        witness_name=witness_name,
        date=timezone.now(),
    )


@login_required
def consent_blank_form(request):
    """Printable BLANK consent form — for a person to sign before capture."""
    statement = get_statement()
    return render(request, "consent_blank_form.html", {
        "statement": statement,
        "version": CURRENT_VERSION,
    })


@login_required
def consent_record(request, borrower_id):
    """Printable record of a person's captured consent (proof)."""
    borrower = get_object_or_404(BorrowerProfile, id=borrower_id)
    consent = DataProcessingConsent.active_for(borrower) or \
        borrower.consents.order_by("-date").first()
    statement = get_statement(consent.statement_version if consent else None)
    return render(request, "consent_record.html", {
        "borrower": borrower,
        "consent": consent,
        "statement": statement,
    })


@login_required
def withdraw_consent(request, borrower_id):
    """A person withdraws their consent (DPA right)."""
    borrower = get_object_or_404(BorrowerProfile, id=borrower_id)
    # only the person themselves (or staff acting on their request) should do this
    if getattr(request.user, "borrower", None) != borrower:
        messages.error(request, "You can only withdraw your own consent.")
        return redirect("borrowers:borrower_index")
    consent = DataProcessingConsent.active_for(borrower)
    if request.method == "POST" and consent:
        consent.withdraw()
        messages.success(request, "Your consent has been withdrawn. This may affect "
                                  "our ability to provide the service.")
    return redirect("borrowers:borrower_index")


@login_required
def my_invitations(request):
    invitations = (GroupInvitation.objects.filter(invited_by=request.user.borrower)
                   .select_related('group', 'invitee').order_by('-sent_at'))
    return render(request, 'groups/my_invitations.html', {'invitations': invitations})


@login_required
def withdraw_invitation(request, invitation_id):
    invitation = get_object_or_404(GroupInvitation, id=invitation_id, invited_by=request.user.borrower)
    if request.method == 'POST':
        if invitation.status == 'pending':
            with transaction.atomic():
                invitation.status = 'withdrawn'
                invitation.responded_at = timezone.now()
                invitation.save()
            messages.success(request, f"Invitation to {invitation.invitee_name} withdrawn.")
        else:
            messages.error(request, f"Cannot withdraw — invitation is {invitation.get_status_display()}.")
        return redirect('groups:my_invitations')
    return render(request, 'groups/invitation_confirm_action.html',
                  {'invitation': invitation, 'action': 'withdraw'})


# =====================================================================
# Join requests  (approval reserved to admin; final say)
# =====================================================================

@login_required
def review_join_request(request, request_id):
    join_request = get_object_or_404(GroupJoinRequest, id=request_id)
    group = join_request.group
 
    # Only the admin can review (final approval is admin-reserved).
    if not is_group_admin(request.user, group):
        messages.error(request, "Only the group admin can review join requests.")
        return redirect('groups:group_detail', group.id)
 
    if request.method == 'POST':
        form = GroupAdminReviewForm(request.POST, instance=join_request)
        if form.is_valid():
            review = form.save(commit=False)
 
            if review.status == 'approved':
                review.decision_date = timezone.now()
                # ACTUALLY add them — idempotent so a double-approve can't
                # create two memberships.
                membership, created = GroupMembership.objects.get_or_create(
                    group=group, borrower=join_request.requester,
                    defaults={"role": "member", "status": "active"},
                )
                ActivityLog.objects.create(
                    group=group, actor=request.user, action="member_added",
                    details=f"{join_request.requester.full_name} approved to join.")
                _notify_applicant(join_request, approved=True)
 
            elif review.status == 'rejected':
                review.decision_date = timezone.now()
                _notify_applicant(join_request, approved=False,
                                  reason=review.rejection_reason if hasattr(review, "rejection_reason") else "")
 
            review.save()
            form.save_m2m()
 
            messages.success(
                request,
                f"Join request for {join_request.requester.full_name} "
                f"marked {review.get_status_display}.")
            return redirect('groups:group_admin_dashboard')   # no kwarg — dashboard derives groups from user
    else:
        form = GroupAdminReviewForm(instance=join_request)
 
    return render(request, 'admin_review_join_request.html', {
        'form': form, 'join_request': join_request, 'group': group,
    })
 
 
def _notify_applicant(join_request, *, approved: bool, reason: str = ""):
    """Tell the applicant the outcome of their join request."""
    requester = join_request.requester
    group = join_request.group
    user = getattr(requester, "user", None)
    if not user:
        return  # invitee-created profile without a user account yet
 
    if approved:
        msg = f"Your request to join {group.name} has been approved. Welcome!"
        cat = "group_update"
    else:
        msg = (f"Your request to join {group.name} was not approved. "
               f"{('Reason: ' + reason + '. ') if reason else ''}"
               f"You may contact the group admin for more.")
        cat = "group_update"
 
    Notification.objects.create(user=user, category=cat, message=msg)
    send_sms(requester.phone_number,
              "group_join_approved" if approved else "group_join_rejected",
              {"name": requester.full_name, "group": group.name,
               "reason": reason or "the admin's decision"})

    
@login_required
@group_admin_required
def pending_join_requests(request):
    borrower = request.user.borrower
    staff_group_ids = GroupMembership.objects.filter(
        borrower=borrower, status="active", role__in=["admin", "sub_admin"]
    ).values_list("group_id", flat=True)
    pending = (GroupJoinRequest.objects.filter(group_id__in=staff_group_ids, status='pending')
               .select_related('group', 'requester'))
    return render(request, 'pending_join_requests.html', {'pending_requests': pending})


@login_required
def approve_join_request(request, request_id):
    join_request = get_object_or_404(GroupJoinRequest, id=request_id, status='pending')
    group = join_request.group
    # FINAL APPROVAL is admin-only (your rule).
    if not is_group_admin(request.user, group):
        messages.error(request, "Only the group administrator can approve join requests.")
        return redirect('groups:group_detail', group.id)

    GroupMembership.objects.create(group=group, borrower=join_request.requester,
                                   role='member', status='active')
    join_request.status = 'approved'
    join_request.decision_date = timezone.now()
    join_request.save()
    ActivityLog.objects.create(group=group, actor=request.user, action="member_added",
                               details=f"{join_request.requester.full_name} approved to join.")
    messages.success(request, f"{join_request.requester.full_name} has been added to {group.name}.")
    return redirect('groups:pending_join_requests')


@login_required
def decline_join_request(request, request_id):
    join_request = get_object_or_404(GroupJoinRequest, id=request_id, status='pending')
    if not is_group_admin(request.user, join_request.group):
        messages.error(request, "Only the group administrator can decline join requests.")
        return redirect('groups:group_detail', join_request.group.id)
    join_request.status = 'declined'
    join_request.decision_date = timezone.now()
    join_request.save()
    messages.warning(request, f"Join request from {join_request.requester.full_name} declined.")
    return redirect('groups:pending_join_requests')


# =====================================================================
# Small helpers
# =====================================================================
def has_borrower_profile(request, user_id):
    exists = BorrowerProfile.objects.filter(user_id=user_id).exists()
    return JsonResponse({'has_profile': exists})




# =====================================================================
# Contributions (claims)  (staff may record; confirmation reserved to treasurer)
# =====================================================================

@login_required
def record_contribution(request, group_id):
    """A member records a contribution CLAIM into the group pool."""
    group = get_object_or_404(BorrowerGroup, id=group_id)

    membership = group_membership(request.user, group)
    if membership is None:
        messages.error(request, "You must be an active member of this group to record a contribution.")
        return redirect("groups:group_detail", group.id)

    # A group must have financial rules set before it accepts money.
    if not getattr(group, "financial_rules", None):
        messages.warning(request, "This group's financial rules aren't set up yet. "
                                  "Ask an admin to configure them before recording contributions.")
        return redirect("groups:group_detail", group.id)

    if request.method == "POST":
        form = GroupContributionClaimForm(request.POST, request.FILES)   # FILES for proof
        if form.is_valid():
            contribution = form.save(commit=False)
            contribution.group = group
            contribution.membership = membership
            contribution.status = "claimed"        # NOT counted until confirmed
            contribution.save()                    # reference auto-generated; pool untouched

            # Notify the money-role members that a claim needs confirming.
            _notify_confirmers(group, membership, contribution)

            messages.success(
                request,
                f"Contribution claim submitted (ref {contribution.reference}). "
                f"It will be confirmed by the treasurer once receipt is verified.")
            return redirect("groups:group_detail", group.id)
    else:
        form = GroupContributionClaimForm()

    return render(request, "record_contribution.html", {"group": group, "form": form})


def _notify_confirmers(group, member_membership, contribution):
    """Notify treasurer/admin/sub_admin that a contribution claim awaits confirmation."""
    MONEY_ROLES = {"admin", "sub_admin", "treasurer"}
    confirmers = group.memberships.filter(status="active", role__in=MONEY_ROLES)
    for m in confirmers:
        user = getattr(m.borrower, "user", None)
        if not user:
            continue
        Notification.objects.create(
            user=user,
            category="group_update",
            message=(f"{member_membership.borrower.full_name} recorded a contribution of "
                     f"M{contribution.amount} (ref {contribution.reference}) to {group.name}. "
                     f"Please confirm receipt."),
        )
        send_sms(confirmers.borrower.phone_number, "group_contribution_claimed",
            {"name": confirmers.borrower.full_name, "amount": contribution.amount,
            "ref": contribution.reference, "group": group.name})



"""
Fedha-Grow — group contribution confirmation (money-role side)
=============================================================
A money-role member (treasurer, admin, or sub_admin) confirms or rejects a
member's contribution CLAIM. Confirmation is what counts it toward the pool.
Mirrors the lender loan-payment confirmation flow.
"""
@login_required
def group_contributions(request, group_id):
    """
    Money-role view of a group's contributions: pending claims (action needed)
    separated from confirmed/rejected history. This is where confirmation happens.
    """
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can manage contributions.")
        return redirect("groups:group_detail", group.id)

    contributions = group.contributions.select_related("membership__borrower").all()
    pending = [c for c in contributions if c.status == "claimed"]
    history = [c for c in contributions if c.status != "claimed"]

    return render(request, "group_contributions.html", {
        "group": group,
        "pending": pending,
        "history": history,
        "pool_total": GroupContribution.confirmed_pool_total(group),
    })

'''
@login_required
@require_POST
def confirm_contribution2(request, contribution_id):
    """Confirm receipt — this counts the contribution toward the pool."""
    contribution = get_object_or_404(
        GroupContribution, id=contribution_id, status="claimed")
    group = contribution.group

    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can confirm contributions.")
        return redirect("groups:group_detail", group.id)

    confirmer = group_membership(request.user, group)
    contribution.confirm(by_membership=confirmer)

    # Notify the member their contribution is confirmed.
    member_user = getattr(contribution.membership.borrower, "user", None)
    if member_user:
        Notification.objects.create(
            user=member_user,
            category="group_update",
            message=(f"Your contribution of M{contribution.amount} (ref {contribution.reference}) "
                     f"to {group.name} has been confirmed."),
        )
        send_sms(contribution.membership.borrower.phone_number, "group_contribution_confirmed",
         {"name": contribution.membership.borrower.full_name, "amount": contribution.amount,
          "ref": contribution.reference, "group": group.name})

    messages.success(request, f"Contribution {contribution.reference} confirmed.")
    return redirect("groups:group_contributions", group.id)
'''

@login_required
@require_POST
def reject_contribution(request, contribution_id):
    """Reject a claim (e.g. not received). The member can correct and resubmit."""
    contribution = get_object_or_404(
        GroupContribution, id=contribution_id, status="claimed")
    group = contribution.group

    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can reject contributions.")
        return redirect("groups:group_detail", group.id)

    confirmer = group_membership(request.user, group)
    reason = (request.POST.get("reason") or "").strip()
    contribution.reject(by_membership=confirmer, reason=reason)

    member_user = getattr(contribution.membership.borrower, "user", None)
    if member_user:
        Notification.objects.create(
            user=member_user,
            category="group_update",
            message=(f"Your contribution claim of M{contribution.amount} (ref {contribution.reference}) "
                     f"to {group.name} could not be confirmed. "
                     f"{('Reason: ' + reason + '. ') if reason else ''}Please check and resubmit."),
        )
        send_sms(contribution.membership.borrower.phone_number, "group_contribution_rejected",
                 {"name": contribution.membership.borrower.full_name, 
                  "amount": contribution.amount,
                  "ref": contribution.reference, 
                  "group": group.name,
                  "reason": reason or "the payment could not be matched"})

    messages.info(request, f"Contribution {contribution.reference} rejected. The member can resubmit.")
    return redirect("groups:group_contributions", group.id)




"""
Fedha-Grow — money confirmation views with separation-of-duties guard
====================================================================
The confirm_contribution / mark_payout_paid views, updated so a money-role
member cannot confirm their OWN money when someone else could do it instead.

Drop these guarded versions in place of the earlier ones.
"""
@login_required
@require_POST
def confirm_contribution(request, contribution_id):
    contribution = get_object_or_404(GroupContribution, id=contribution_id, status="claimed")
    group = contribution.group

    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can confirm contributions.")
        return redirect("groups:group_detail", group.id)

    confirmer = group_membership(request.user, group)

    # --- separation of duties: can't confirm your own money if someone else can ---
    allowed, requires_other, reason = can_confirm_for(
        confirmer, contribution.membership, group)
    if not allowed:
        messages.error(request, reason)
        return redirect("groups:group_contributions", group.id)

    contribution.confirm(by_membership=confirmer)

    member_user = getattr(contribution.membership.borrower, "user", None)
    if member_user:
        Notification.objects.create(
            user=member_user, category="group_update",
            message=(f"Your contribution of M{contribution.amount} (ref {contribution.reference}) "
                     f"to {group.name} has been confirmed."))
        # send_sms(...)

    messages.success(request, f"Contribution {contribution.reference} confirmed.")
    return redirect("groups:group_contributions", group.id)

"""
Fedha-Grow — separation of duties (self-dealing guard)
=====================================================
The real conflict-of-interest risk isn't multi-group admin — it's a money-role
member confirming their OWN money. This guard enforces separation of duties:
a person can't confirm their own contribution or authorise their own payout,
UNLESS the group is too small to have anyone else who could (a genuine
one-money-person group), in which case it's allowed but flagged for the
transparent ledger to surface.

The transparent member-facing ledger is the backstop: even where a small group
must self-confirm, every member sees it, so it can't be hidden.
"""

MONEY_ROLES = {"admin", "sub_admin", "treasurer"}


def other_money_role_exists(group, excluding_membership):
    """
    Is there ANOTHER active money-role member who could confirm instead of the
    person themselves? Determines whether self-confirmation is avoidable.
    """
    return group.memberships.filter(
        status="active", role__in=MONEY_ROLES
    ).exclude(id=excluding_membership.id).exists()


def can_confirm_for(confirmer_membership, subject_membership, group):
    """
    May `confirmer_membership` confirm money belonging to `subject_membership`?

    Rules:
      - Confirming someone ELSE's money: always allowed (they hold a money role).
      - Confirming your OWN money: allowed ONLY if no other money-role member
        exists (tiny group). Otherwise blocked — someone else must confirm.

    Returns (allowed: bool, requires_other: bool, reason: str).
    `requires_other` is True when it was blocked specifically because another
    money-role member is available and should do it instead.
    """
    if confirmer_membership is None:
        return False, False, "You don't have permission to confirm group money."

    is_self = (confirmer_membership.id == subject_membership.id)

    if not is_self:
        return True, False, ""

    # self-confirmation: only if there's genuinely no one else
    if other_money_role_exists(group, confirmer_membership):
        return (False, True,
                "You can't confirm your own contribution or payout. "
                "Another treasurer or admin must confirm it — this keeps the "
                "group's money above suspicion.")
    # sole money-role person in a small group: allowed, but it's on the record
    return True, False, ""



@login_required
@require_POST
def mark_payout_paid(request, payout_id):
    payout = get_object_or_404(GroupPayout, id=payout_id, status="pending")
    group = payout.group

    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can mark payouts paid.")
        return redirect("groups:group_detail", group.id)

    authoriser = group_membership(request.user, group)

    # --- separation of duties: can't authorise a payout TO YOURSELF if
    #     someone else could authorise it instead ---
    if payout.recipient is not None:
        allowed, requires_other, reason = can_confirm_for(
            authoriser, payout.recipient, group)
        if not allowed:
            messages.error(request, reason.replace("contribution or payout", "payout"))
            return redirect("groups:payouts", group.id)

    payout.mark_paid(by_membership=authoriser)

    # advance rotation only on confirmed disbursement
    rules = getattr(group, "financial_rules", None)
    if rules and payout.kind == "rotation":
        rules.advance_rotation()

    if payout.recipient:
        user = getattr(payout.recipient.borrower, "user", None)
        if user:
            Notification.objects.create(
                user=user, category="group_update",
                message=(f"You've received a payout of M{payout.amount} "
                         f"(ref {payout.reference}) from {group.name}."))
            # send_sms(...)

    messages.success(request, f"Payout {payout.reference} marked paid. Rotation advanced.")
    return redirect("groups:payouts", group.id)


@login_required
def group_ledger(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
 
    my_membership = group_membership(request.user, group)
    if my_membership is None:
        messages.error(request, "You must be an active member of this group to view its ledger.")
        return redirect("groups:group_detail", group.id)
 
    rules = getattr(group, "financial_rules", None)
 
    # --- confirmed pool (the real balance) ---
    pool_total = GroupContribution.confirmed_pool_total(group)
    pending_total = GroupContribution.claimed_total(group) if hasattr(GroupContribution, "claimed_total") \
        else group.contributions.filter(status="claimed").aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
 
    # --- per-member confirmed totals (who has contributed) ---
    active_memberships = group.memberships.filter(status="active").select_related("borrower")
    confirmed_by_member = {
        row["membership"]: row["total"]
        for row in group.contributions.filter(status="confirmed")
        .values("membership").annotate(total=Sum("amount"))
    }
    member_rows = []
    for m in active_memberships:
        member_rows.append({
            "membership": m,
            "name": m.borrower.full_name,
            "role": effective_role(m),
            "confirmed_total": confirmed_by_member.get(m.id, Decimal("0.00")),
            "is_me": (m.id == my_membership.id),
        })
    # sort: highest contributors first (gently motivating, and transparent)
    member_rows.sort(key=lambda r: r["confirmed_total"], reverse=True)
 
    # --- my own history ---
    my_contributions = group.contributions.filter(membership=my_membership).order_by("-date_paid")
    my_confirmed = GroupContribution.member_confirmed_total(my_membership) \
        if hasattr(GroupContribution, "member_confirmed_total") \
        else my_contributions.filter(status="confirmed").aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
 
    # --- rotation: whose turn (ROSCA only) ---
    next_recipient = None
    if rules and rules.payout_type == "rotating" and rules.rotation_order:
        next_id = rules.next_recipient_membership_id if hasattr(rules, "next_recipient_membership_id") else None
        if next_id:
            next_recipient = active_memberships.filter(id=next_id).first()
 
    # --- pending claims (shown, but clearly not counted) ---
    pending_claims = (group.contributions.filter(status="claimed")
                      .select_related("membership__borrower").order_by("-date_paid"))
 
    return render(request, "group_ledger.html", {
        "group": group,
        "rules": rules,
        "pool_total": pool_total,
        "pending_total": pending_total,
        "member_rows": member_rows,
        "member_count": active_memberships.count(),
        "my_membership": my_membership,
        "my_contributions": my_contributions,
        "my_confirmed": my_confirmed,
        "next_recipient": next_recipient,
        "pending_claims": pending_claims,
        "cycle_number": getattr(rules, "cycle_number", None) if rules else None,
    })

# =====================================================================
# Rotation payouts (ROSCA)
# =====================================================================
 
@login_required
def rotation_order(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if not is_group_admin(request.user, group):
        messages.error(request, "Only the group administrator can arrange the rotation order.")
        return redirect("groups:group_detail", group.id)
 
    rules, _ = GroupFinancialRules.objects.get_or_create(group=group)
    if rules.payout_type != "rotating":
        messages.info(request, "Rotation order applies only to rotating (ROSCA) payouts.")
        return redirect("groups:group_financial_rules", group.id)
 
    active = list(group.memberships.filter(status="active").select_related("borrower"))
    by_id = {m.id: m for m in active}
 
    # Build the ordered list: saved order first (still-active only), then any
    # active members not yet placed (new members appended at the end).
    saved = rules.rotation_order or []
    ordered = [by_id[mid] for mid in saved if mid in by_id]
    placed = set(saved)
    ordered += [m for m in active if m.id not in placed]
 
    if request.method == "POST":
        # order arrives as a comma-separated list of membership ids
        raw = request.POST.get("order", "")
        try:
            new_order = [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            messages.error(request, "Could not read the new order. Please try again.")
            return redirect("groups:rotation_order", group.id)
 
        # keep only ids that are genuinely active members of this group
        new_order = [mid for mid in new_order if mid in by_id]
        rules.rotation_order = new_order
        # reset the pointer if the order changed materially
        if rules.current_rotation_index >= len(new_order):
            rules.current_rotation_index = 0
        rules.save(update_fields=["rotation_order", "current_rotation_index", "updated_at"])
        messages.success(request, "Rotation order saved.")
        return redirect("groups:group_detail", group.id)
 
    return render(request, "rotation_order.html", {
        "group": group,
        "rules": rules,
        "ordered_members": ordered,
        "current_index": rules.current_rotation_index,
    })

# =====================================================================
# Payouts (disbursements)
# =====================================================================
@login_required
def payouts(request, group_id):
    """List payouts; offer to create the next rotation payout."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can manage payouts.")
        return redirect("groups:group_detail", group.id)
 
    rules = getattr(group, "financial_rules", None)
    next_recipient = None
    if rules and rules.payout_type == "rotating" and rules.rotation_order:
        next_id = rules.next_recipient_membership_id
        if next_id:
            next_recipient = group.memberships.filter(id=next_id, status="active").first()
 
    return render(request, "group_payouts.html", {
        "group": group,
        "rules": rules,
        "pool": pool_balance(group),
        "next_recipient": next_recipient,
        "pending": group.payouts.filter(status="pending").select_related("recipient__borrower"),
        "history": group.payouts.exclude(status="pending").select_related("recipient__borrower"),
    })
 

 #=====================================================================
 # Create / mark paid / cancel payouts (treasurer only)
 # ==================================================================== 
@login_required
@require_POST
def create_rotation_payout(request, group_id):
    """Create a PENDING payout for the current-turn member."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can create payouts.")
        return redirect("groups:group_detail", group.id)
 
    rules = get_object_or_404(GroupFinancialRules, group=group)
    if rules.payout_type != "rotating" or not rules.rotation_order:
        messages.error(request, "This group doesn't have a rotation set up.")
        return redirect("groups:payouts", group.id)
 
    next_id = rules.next_recipient_membership_id
    recipient = group.memberships.filter(id=next_id, status="active").first()
    if not recipient:
        messages.error(request, "Couldn't determine whose turn it is. Check the rotation order.")
        return redirect("groups:rotation_order", group.id)
 
    # Amount defaults to the current pool; treasurer may override.
    raw_amount = (request.POST.get("amount") or "").strip()
    if raw_amount:
        try:
            amount = Decimal(raw_amount)
        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid amount.")
            return redirect("groups:payouts", group.id)
    else:
        amount = pool_balance(group)
 
    if amount <= 0:
        messages.error(request, "There's nothing in the pool to pay out yet.")
        return redirect("groups:payouts", group.id)
 
    payout = GroupPayout.objects.create(
        group=group, recipient=recipient, amount=amount, kind="rotation",
        status="pending", cycle_number=rules.cycle_number,
        authorised_by=group_membership(request.user, group),
    )
    messages.success(request, f"Payout {payout.reference} created for {recipient.borrower.full_name}. "
                              f"Mark it paid once you've disbursed the funds.")
    return redirect("groups:payouts", group.id)
 
''' 
@login_required
@require_POST
def mark_payout_paid(request, payout_id):
    """
    Treasurer confirms the disbursement happened. THIS is what advances the
    rotation — the pointer moves only when money genuinely went out.
    """
    payout = get_object_or_404(GroupPayout, id=payout_id, status="pending")
    group = payout.group
    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can mark payouts paid.")
        return redirect("groups:group_detail", group.id)
 
    payout.mark_paid(by_membership=group_membership(request.user, group))
 
    # Advance the rotation ONLY now (on confirmed disbursement).
    rules = getattr(group, "financial_rules", None)
    if rules and payout.kind == "rotation":
        rules.advance_rotation()
 
    # Notify the recipient.
    if payout.recipient:
        user = getattr(payout.recipient.borrower, "user", None)
        if user:
            Notification.objects.create(
                user=user, category="group_update",
                message=(f"You've received a payout of M{payout.amount} (ref {payout.reference}) "
                         f"from {group.name}."))
            send_sms(payout.recipient.borrower.phone_number, "group_payout_paid",
                      {"name": payout.recipient.borrower.full_name, "amount": payout.amount,
                        "ref": payout.reference, "group": group.name})
 
    messages.success(request, f"Payout {payout.reference} marked paid. Rotation advanced to the next member.")
    return redirect("groups:payouts", group.id)
 '''
 
@login_required
@require_POST
def cancel_payout(request, payout_id):
    """Cancel a pending payout (does NOT advance rotation)."""
    payout = get_object_or_404(GroupPayout, id=payout_id, status="pending")
    group = payout.group
    if not can_handle_money(request.user, group):
        messages.error(request, "Only the treasurer or an admin can cancel payouts.")
        return redirect("groups:group_detail", group.id)
    payout.status = "cancelled"
    payout.save(update_fields=["status"])
    messages.info(request, f"Payout {payout.reference} cancelled.")
    return redirect("groups:payouts", group.id)


@login_required
@group_member_required
def group_meetings(request, group_id):
    """The group's meeting record — visible to every member."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    meetings = group.meetings.all()   # model orders by -date via Meta or add order_by
    return render(request, "group_meetings.html", {
        "group": group,
        "meetings": meetings,
        "can_manage": is_group_staff(request.user, group),
    })


@login_required
@group_staff_required
def create_meeting(request, group_id):
    """Staff log a meeting (and optionally its minutes)."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    if request.method == "POST":
        form = GroupMeetingForm(request.POST, request.FILES)   # FILES for minutes upload
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.group = group
            meeting.created_by = request.user       # GroupMeeting.created_by -> AUTH_USER_MODEL
            meeting.save()
            ActivityLog.objects.create(
                group=group, actor=request.user, action="meeting_created",
                details=f"Meeting '{meeting.title}' on {meeting.date}.")
            messages.success(request, "Meeting recorded.")
            return redirect("groups:group_meetings", group.id)
    else:
        form = GroupMeetingForm()
    return render(request, "create_meeting.html", {"group": group, "form": form})


"""
Fedha-Grow — bulk member import (commit + views)
================================================
The confirm half: after the agent reviews the preview, this creates PROFILES +
GROUP MEMBERSHIPS + pending INVITATIONS for the valid rows. It does NOT create
accounts or consent — each person activates and consents themselves via the
invitation link (SMS_TEST_MODE logs the link during testing).

Flow:
  1. import_upload   — agent uploads xlsx -> parse + classify -> preview page
  2. import_confirm  — agent confirms -> commit valid rows -> invitations sent
"""

@login_required
@group_staff_required
def import_upload(request, group_id):
    """Upload an xlsx, parse + classify, show a preview. Writes nothing."""
    group = get_object_or_404(BorrowerGroup, id=group_id)

    if request.method == "POST" and request.FILES.get("file"):
        preview = parse_workbook(request.FILES["file"])
        if not preview.header_ok:
            messages.error(request, preview.header_error)
            return redirect("groups:import_upload", group.id)

        classify_rows(preview, group)

        # stash the importable rows in session for the confirm step
        request.session[f"import_{group.id}"] = [
            {"data": r.data, "classification": r.classification,
             "existing_borrower_id": r.existing_borrower_id}
            for r in preview.importable
        ]
        return render(request, "member_import_preview.html", {
            "group": group,
            "preview": preview,
        })

    return render(request, "member_import_upload.html", {
        "group": group,
        "columns": EXPECTED_COLUMNS,
    })


@login_required
@group_staff_required
def import_confirm(request, group_id):
    """Commit the previewed rows: create profiles + memberships + invitations."""
    group = get_object_or_404(BorrowerGroup, id=group_id)
    stash = request.session.get(f"import_{group.id}")
    if not stash:
        messages.error(request, "Nothing to import — please upload a file first.")
        return redirect("groups:import_upload", group.id)

    if request.method != "POST":
        return redirect("groups:import_upload", group.id)

    from borrowers.models import BorrowerProfile
    inviter = request.user.borrower
    created, linked, invited = 0, 0, 0

    with transaction.atomic():
        for row in stash:
            data = row["data"]
            phone = data.get("phone_number")

            # resolve or create the profile (dedupe by phone, re-checked here)
            if row["classification"] == "existing" and row["existing_borrower_id"]:
                borrower = BorrowerProfile.objects.filter(id=row["existing_borrower_id"]).first()
                if borrower:
                    linked += 1
                else:
                    borrower = _create_stub(BorrowerProfile, data)
                    created += 1
            else:
                # guard against a race: someone with this phone created since preview
                borrower = BorrowerProfile.objects.filter(phone_number=phone).first()
                if borrower:
                    linked += 1
                else:
                    borrower = _create_stub(BorrowerProfile, data)
                    created += 1

            # add to the group (idempotent)
            GroupMembership.objects.get_or_create(
                group=group, borrower=borrower,
                defaults={"role": "member", "status": "active"})

            # create a pending invitation so they can activate + consent
            # (skip if they already have an account — nothing to activate)
            if not borrower.user_id:
                invitation = GroupInvitation.objects.create(
                    group=group, invited_by=inviter, invitee=borrower,
                    invitee_name=borrower.full_name,
                    invitee_phone=borrower.phone_number,
                    invitee_email=(data.get("email") or ""),
                )
                invited += 1
                # send_sms(borrower.phone_number, "group_invitation", {
                #     "name": borrower.full_name, "group": group.name,
                #     "code": invitation.invitation_code,
                #     "url": request.build_absolute_uri(invitation.get_activation_url())})

    # clear the stash
    request.session.pop(f"import_{group.id}", None)

    messages.success(
        request,
        f"Import complete: {created} new profile(s), {linked} linked to existing people, "
        f"{invited} invitation(s) created.")
    return redirect("groups:group_members", group.id)


def _create_stub(BorrowerProfile, data):
    """Create a minimal profile stub from a validated row. Person completes the rest."""
    fields = {"full_name": data.get("full_name", ""),
              "phone_number": data.get("phone_number", "")}
    # optional captured fields, only if your model has them (guarded)
    for f in ("id_number", "income",
              "employer_name", "employment_position", "date_of_birth"):
        val = data.get(f)
        if val and hasattr(BorrowerProfile, f):
            fields[f] = val
    return BorrowerProfile.objects.create(**fields)



"""
Fedha-Grow — import template download
=====================================
Streams a blank .xlsx with the exact header row the importer expects, plus a
greyed example row showing the format. Agents fill this and upload it back,
so the columns always match what parse_workbook() reads.
 
Kept in sync with EXPECTED_COLUMNS in member_import_core.py — if you change the
columns there, this template updates automatically (it imports the same list).
"""

# a friendly one-row example so agents see the expected format
_EXAMPLE = {
    "full_name": "Thabo Mokoena",
    "phone_number": "+26658000001",
    "email": "thabo@example.com",
    "id_number": "9001011234088",
    "date_of_birth": "1990-01-01",
    "income": "5000",
    "monthly_expenses": "3200",
    "employer_name": "Example Employer",
    "employment_position": "Clerk",
}
 
 
@login_required
@group_staff_required
def import_template(request, group_id):
    group = get_object_or_404(BorrowerGroup, id=group_id)
 
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Members"
 
    header_fill = PatternFill(start_color="028090", end_color="028090", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    req_font = Font(bold=True, color="FFFF00")   # required columns marked
 
    # header row
    for col_idx, col in enumerate(EXPECTED_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col)
        cell.fill = header_fill
        cell.font = req_font if col in REQUIRED_COLUMNS else header_font
        ws.column_dimensions[cell.column_letter].width = max(len(col) + 4, 16)
 
    # example row (row 2) — greyed, so agents can see the format then overwrite it
    example_font = Font(italic=True, color="999999")
    for col_idx, col in enumerate(EXPECTED_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=_EXAMPLE.get(col, ""))
        cell.font = example_font
 
    # a note row below (row 4)
    ws.cell(row=4, column=1,
            value="full_name and phone_number are required on every row. "
                  "Delete this note and the example row before uploading. "
                  "Extra columns are ignored.").font = Font(italic=True, color="A32C2C")
 
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
 
    filename = f"fedha-grow-members-template-{group.id}.xlsx"
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp