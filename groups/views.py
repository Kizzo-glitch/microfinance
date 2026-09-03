
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from decimal import Decimal

from django.views.decorators.http import require_POST

from borrowers.models import BorrowerProfile
from borrowers.forms import BorrowerProfileForm
from loans.models import Loan, Notification
from .models import (
    BorrowerGroup, GroupMembership, GroupConstitution, GroupInvitation,
    GroupJoinRequest, GroupDocument, ActivityLog,
    GroupFinancialRules, GroupContribution
)
from .forms import (
    BorrowerGroupRegistrationForm, BorrowerGroupForm,
    GroupConstitutionForm, GroupContributionClaimForm, GroupInvitationForm, BorrowerMiniForm, ActivationForm,
    GroupFinancialRulesForm,
)
from .group_permissions import (
    group_admin_required, group_member_required, group_staff_required,
    group_admin_only, is_group_staff, is_group_admin, group_membership,
    check_admin_inactivity, claim_acting_admin, can_claim_acting_admin, promote, 
    can_handle_money, effective_role,
)
from comms.sms.service import send_sms






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


@login_required
@group_staff_required
def manage_members(request, group_id):
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
                return render(request, 'invite_borrower.html',
                              {'group': group, 'form': form, 'profile_form': profile_form})

            invitation.invitee = borrower
            invitation.invitee_name = borrower.full_name
            invitation.invitee_phone = borrower.phone_number
            invitation.invitee_email = (borrower.user.email if borrower.user else email)
            invitation.save()

            activation_url = request.build_absolute_uri(invitation.get_activation_url())
            # send_sms(invitation.invitee_phone, "group_invitation",
            #          {"name": invitation.invitee_name, "group": group.name,
            #           "code": invitation.invitation_code, "url": activation_url})
            invitation.sms_sent = True
            invitation.sms_sent_at = timezone.now()
            invitation.save()

            messages.success(request, f"Invitation sent. Code: {invitation.invitation_code}")
            return redirect('groups:group_detail', group.id)
        messages.error(request, "Please correct the errors below.")
    else:
        form = GroupInvitationForm()
        profile_form = BorrowerMiniForm()
    return render(request, 'invite_borrower.html',
                  {'group': group, 'form': form, 'profile_form': profile_form})


def activate_invite(request, code=None):
    """Public — invitee may not have an account yet."""
    invitation_code = (code or request.POST.get('invitation_code') or '').strip().upper()
    if not invitation_code:
        messages.error(request, "Missing invitation code.")
        return render(request, "activate_invite.html", {'form': ActivationForm()})

    invite = get_object_or_404(GroupInvitation, invitation_code=invitation_code, status='pending')
    borrower_profile = invite.invitee
    parts = invite.invitee_name.split()
    first_name, last_name = parts[0], (parts[-1] if len(parts) > 1 else "")

    if request.method == "POST":
        form = ActivationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            email = form.cleaned_data.get('email') or invite.invitee_email
            phone = form.cleaned_data.get('phone_number') or invite.invitee_phone

            if borrower_profile.user:
                user = borrower_profile.user
                user.username, user.email = username, email
                user.first_name, user.last_name = first_name, last_name
                if hasattr(user, "phone_number"):
                    user.phone_number = phone
                user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(username=username, email=email, password=password,
                                                 first_name=first_name, last_name=last_name)
                if hasattr(user, "phone_number"):
                    user.phone_number = phone
                    user.save()
                borrower_profile.user = user
                borrower_profile.save()

            invite.status = 'accepted'
            invite.responded_at = timezone.now()
            invite.save()

            GroupMembership.objects.create(
                group=invite.group, borrower=borrower_profile, role='member',
                status='active', verification_status='identity_verified',
                joined_date=timezone.now())

            login(request, user)
            messages.success(request, f"Welcome {borrower_profile.full_name}, your account is now active.")
            return redirect("borrowers:borrower_index")
    else:
        form = ActivationForm(initial={'email': invite.invitee_email, 'phone_number': invite.invitee_phone,
                                       'first_name': first_name, 'last_name': last_name})
    return render(request, "activate_invite.html",
                  {"form": form, "invite": invite, "borrower_profile": borrower_profile})


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
        send_sms(m.borrower.phone_number, "group_contribution_claimed", {...})


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


@login_required
@require_POST
def confirm_contribution(request, contribution_id):
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
        send_sms(contribution.membership.borrower.phone_number,
                  "group_contribution_confirmed", {...})

    messages.success(request, f"Contribution {contribution.reference} confirmed.")
    return redirect("groups:group_contributions", group.id)


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
        send_sms(contribution.membership.borrower.phone_number,
		 "group_contribution_rejected", {...})

    messages.info(request, f"Contribution {contribution.reference} rejected. The member can resubmit.")
    return redirect("groups:group_contributions", group.id)



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