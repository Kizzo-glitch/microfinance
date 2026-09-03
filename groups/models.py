import uuid
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.conf import settings

from decimal import Decimal
from loans.references import generate_reference

class BorrowerGroup(models.Model):
    """
    Base model for all group types - respects existing structures
    while enabling digital lending
    """
    
    GROUP_TYPES = [
        ('stokvel', 'Stokvel (Savings Club)'),
        ('employer_union', 'Employer Union/Workplace Group'),
        ('burial_society', 'Burial Society'),
        ('savings_group', 'Village Savings Group'),
        ('custom', 'Custom Group'),
    ]
    
    GROUP_STATUS = [
        ('draft', 'Draft - Being Formed'),
        ('formation', 'Formation - Gathering Members'),
        ('verification', 'Verification - Being Verified'),
        ('active', 'Active - Can Borrow'),
        ('suspended', 'Suspended - Issues Present'),
        ('trusted', 'Trusted - Proven Track Record'),
        ('inactive', 'Inactive'),
    ]
    ECONOMIC_ACTIVITY_CHOICES = [
        ("none",     "General savings (no shared activity)"),
        ("farming",  "Farming / agriculture"),
        ("trading",  "Trading / retail"),
        ("services", "Services"),
        ("mixed",    "Mixed activities"),
    ]
    
    # Basic Info
    name = models.CharField(max_length=200)
    group_type = models.CharField(max_length=50, choices=GROUP_TYPES)
    description = models.TextField()
    
    # Location (important for Lesotho context)
    district = models.CharField(max_length=100)  # Maseru, Leribe, etc.
    community_council = models.CharField(max_length=200, blank=True)
    village = models.CharField(max_length=200, blank=True)
    
    # Leadership
    admin = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.PROTECT, related_name='administered_groups')
    sub_admins = models.ManyToManyField('borrowers.BorrowerProfile', related_name='co_administered_groups', blank=True)
    
    # Status & Lifecycle
    status = models.CharField(max_length=50, choices=GROUP_STATUS, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    
    # Traditional group metadata
    established_year = models.IntegerField(null=True, blank=True, help_text="When did this group originally form? (Even if pre-digital)")
    meeting_day = models.CharField(max_length=50, blank=True, help_text="e.g., 'Every Friday', 'Last Sunday of month'")
    meeting_location = models.CharField(max_length=300, blank=True)
    
    # Cultural integration
    chief_endorsed = models.BooleanField(default=False)
    chief_name = models.CharField(max_length=200, blank=True)
    chief_letter = models.FileField(upload_to='group_documents/chief_letters/', null=True, blank=True)
    
    # Group rules reference
    #constitution = models.OneToOneField('GroupConstitution', on_delete=models.SET_NULL, null=True, blank=True, related_name='group')
    
    # Metrics
    member_count = models.IntegerField(default=0)
    total_loans_taken = models.IntegerField(default=0)
    total_amount_borrowed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    economic_activity = models.CharField(
        max_length=20, choices=ECONOMIC_ACTIVITY_CHOICES, default="none",
        help_text="The group's shared economic activity, if any. Anchors future "
                  "value-chain / merchant data. 'none' for general savings groups.",
    )
    activity_description = models.CharField(
        max_length=255, blank=True,
        help_text="Optional detail, e.g. 'Maize farmers, Leribe' or 'Maseru market traders'.",
    )
 
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.get_group_type_display()})"


"""
Fedha-Grow — group financial rules (primitives, not types)
==========================================================
Replaces GroupTypeSpecificSettings. Instead of a column-set per group type
(stokvel_*, society_*, savings_group_*), every group has the SAME two
primitives configured with different VALUES:
 
    - a contribution rule (how money comes in)
    - a payout rule       (how money goes out)
 
A stokvel, burial society, ROSCA, and village bank differ only in the values
of these two rules — not in schema. Adding a new "type" is a new preset, never
a migration.
 
  ROSCA / stokvel   = contribution(monthly, M200) + payout(rotating)
  burial society    = contribution(monthly, M50)  + payout(event_triggered)
  year-end stokvel  = contribution(monthly, M200) + payout(end_of_term)
  village bank      = contribution(monthly, share) + payout(internal_lending)
 
`group_type` on BorrowerGroup stays as a LABEL/preset for display and for
seeding sensible defaults — it does not determine the schema.
 
MONEY NOTE: these rules describe amounts and schedules. Funds are NOT held by
the platform — the group's money lives in the group's own account. This model
is the ledger's rulebook, not a wallet.
"""

 
class GroupFinancialRules(models.Model):
    """One row per group. The contribution + payout primitives."""
 
    group = models.OneToOneField(
        "groups.BorrowerGroup", on_delete=models.CASCADE,
        related_name="financial_rules",
    )
 
    # ---------------- contribution rule (money in) ----------------
    FREQUENCY_CHOICES = [
        ("weekly",    "Weekly"),
        ("bi_weekly", "Bi-weekly"),
        ("monthly",   "Monthly"),
        ("quarterly", "Quarterly"),
        ("custom",    "Custom / irregular"),
    ]
    contribution_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Expected contribution per member per cycle.",
    )
    contribution_frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default="monthly",
    )
    contribution_flexible = models.BooleanField(
        default=False,
        help_text="If true, members may contribute variable amounts (e.g. share-based savings groups).",
    )
 
    # ---------------- payout rule (money out) ----------------
    PAYOUT_CHOICES = [
        ("rotating",        "Rotating (ROSCA — each member takes the pot in turn)"),
        ("event_triggered", "Event-triggered (e.g. burial society payout on a death)"),
        ("end_of_term",     "End-of-term (save through a cycle, share out at the end)"),
        ("internal_lending","Internal lending (pool is lent to members at interest)"),
        ("none",            "No structured payout"),
    ]
    payout_type = models.CharField(
        max_length=20, choices=PAYOUT_CHOICES, default="rotating",
    )
 
    # -- rotating (ROSCA) params — the common case --
    rotation_order = models.JSONField(
        null=True, blank=True,
        help_text="Ordered list of membership IDs for the payout rotation.",
    )
    current_rotation_index = models.PositiveIntegerField(
        default=0, help_text="Whose turn it is — index into rotation_order.",
    )
    cycle_number = models.PositiveIntegerField(
        default=1, help_text="Which full rotation the group is on.",
    )
 
    # -- event_triggered (burial society) params --
    payout_per_event = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Fixed payout amount when the trigger event occurs.",
    )
 
    # -- end_of_term params --
    term_end_date = models.DateField(
        null=True, blank=True, help_text="When the cycle shares out.",
    )
 
    # -- internal_lending (village bank) params --
    internal_interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Interest % on loans made from the pool.",
    )
 
    # ---------------- shared destination (funds never through us) ----------------
    # Where the group's pooled money actually lives. The platform records and
    # reconciles against this; it does not hold the funds.
    payout_destination_note = models.CharField(
        max_length=255, blank=True,
        help_text="How/where the group holds its funds (e.g. 'Group bank account at X', "
                  "'Treasurer-managed mobile-money account'). Recorded, not held by the platform.",
    )
 
    updated_at = models.DateTimeField(auto_now=True)
 
    def __str__(self):
        return f"Financial rules for {self.group.name} ({self.get_payout_type_display()})"
 
    # ---- helpers for the common (rotating) case ----
    @property
    def next_recipient_membership_id(self):
        """Membership id whose turn it is in the rotation, or None."""
        if self.payout_type != "rotating" or not self.rotation_order:
            return None
        order = self.rotation_order
        if 0 <= self.current_rotation_index < len(order):
            return order[self.current_rotation_index]
        return None
 
    def advance_rotation(self):
        """Move to the next member; wrap to a new cycle at the end."""
        if not self.rotation_order:
            return
        self.current_rotation_index += 1
        if self.current_rotation_index >= len(self.rotation_order):
            self.current_rotation_index = 0
            self.cycle_number += 1
        self.save(update_fields=["current_rotation_index", "cycle_number", "updated_at"])


"""
Fedha-Grow — group money movement
=================================
Contributions (money in) and payouts (money out) for groups.

Same discipline as individual loan payments, for the same reason: the platform
does NOT hold the group's funds. A member pays the group externally; the record
is a CLAIM until the group's treasurer/admin CONFIRMS receipt. Only confirmation
counts toward the member's contribution record and the group pool figure.

This keeps the platform a transparent LEDGER, not a custodian — critical for
groups, where pooled funds would otherwise raise deposit-taking concerns.

Everything carries a reference, so contributions and payouts are traceable and
reconcilable — the same connective tissue as the rest of the platform.
"""

class GroupContribution(models.Model):
    """A member's contribution into the group pool. Claim -> confirm."""

    STATUS_CHOICES = [
        ("claimed",   "Claimed (awaiting confirmation)"),
        ("confirmed", "Confirmed received"),
        ("rejected",  "Rejected (not received)"),
    ]
    METHOD_CHOICES = [
        ("bank",    "Bank transfer"),
        ("mpesa",   "M-Pesa"),
        ("ecocash", "EcoCash"),
        ("cash",    "Cash"),
        ("gateway", "In-app payment"),
    ]

    group = models.ForeignKey("groups.BorrowerGroup", on_delete=models.CASCADE,
                              related_name="contributions")
    membership = models.ForeignKey("groups.GroupMembership", on_delete=models.CASCADE,
                                   related_name="contributions")

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="claimed")

    reference          = models.CharField(max_length=24, unique=True, editable=False,
                                          null=True, blank=True)
    external_reference = models.CharField(max_length=120, blank=True,
                                          help_text="Member's own bank/mobile-money txn reference.")
    proof = models.FileField(upload_to="group_contribution_proofs/", null=True, blank=True)

    # which cycle/period this contribution is for (loose — a full schedule is later)
    period_label = models.CharField(max_length=40, blank=True,
                                    help_text="e.g. '2026-08' or 'Cycle 3' — which period this covers.")

    date_paid    = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey("groups.GroupMembership", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="contributions_confirmed",
                                     help_text="The treasurer/admin membership who confirmed receipt.")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_paid"]

    def __str__(self):
        return f"{self.reference or 'contribution'} — M{self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference(GroupContribution, "reference", prefix="FGC")
        super().save(*args, **kwargs)   # does NOT move any pool figure; confirm() does

    def confirm(self, by_membership=None):
        if self.status == "confirmed":
            return
        self.status = "confirmed"
        self.confirmed_at = timezone.now()
        if by_membership is not None:
            self.confirmed_by = by_membership
        self.save(update_fields=["status", "confirmed_at", "confirmed_by"])

    def reject(self, by_membership=None, reason=""):
        self.status = "rejected"
        if by_membership is not None:
            self.confirmed_by = by_membership
        if reason:
            self.note = reason[:255]
        self.save(update_fields=["status", "confirmed_by", "note"])

    # ---- pool totals: CONFIRMED only ----
    @staticmethod
    def confirmed_pool_total(group) -> Decimal:
        return group.contributions.filter(status="confirmed").aggregate(
            total=models.Sum("amount"))["total"] or Decimal("0.00")

    @staticmethod
    def member_confirmed_total(membership) -> Decimal:
        return membership.contributions.filter(status="confirmed").aggregate(
            total=models.Sum("amount"))["total"] or Decimal("0.00")


class GroupPayout(models.Model):
    """
    Money leaving the pool — a ROSCA rotation payout, a burial payout, an
    end-of-term share, or an internal loan disbursement. Recorded and confirmed;
    funds move outside the platform.
    """

    STATUS_CHOICES = [
        ("pending",   "Pending"),
        ("paid",      "Paid (confirmed sent)"),
        ("cancelled", "Cancelled"),
    ]
    PAYOUT_KIND = [
        ("rotation",   "Rotation payout (ROSCA)"),
        ("event",      "Event payout (e.g. burial)"),
        ("share_out",  "End-of-term share-out"),
        ("loan",       "Internal loan disbursement"),
        ("other",      "Other"),
    ]

    group = models.ForeignKey("groups.BorrowerGroup", on_delete=models.CASCADE,
                              related_name="payouts")
    recipient = models.ForeignKey("groups.GroupMembership", on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="payouts_received",
                                  help_text="Member receiving the payout (blank for a group-external payout).")

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind   = models.CharField(max_length=12, choices=PAYOUT_KIND, default="rotation")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    reference = models.CharField(max_length=24, unique=True, editable=False,
                                 null=True, blank=True)
    cycle_number = models.PositiveIntegerField(null=True, blank=True,
                                               help_text="Rotation cycle this payout belongs to, if applicable.")

    authorised_by = models.ForeignKey("groups.GroupMembership", on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="payouts_authorised")
    date_due  = models.DateField(null=True, blank=True)
    date_paid = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'payout'} — M{self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference(GroupPayout, "reference", prefix="FGO")
        super().save(*args, **kwargs)

    def mark_paid(self, by_membership=None):
        self.status = "paid"
        self.date_paid = timezone.now()
        if by_membership is not None:
            self.authorised_by = by_membership
        self.save(update_fields=["status", "date_paid", "authorised_by"])



"""
class GroupTypeSpecificSettings(models.Model):
   
    group = models.OneToOneField(BorrowerGroup, on_delete=models.CASCADE, related_name='type_settings')
    
    # === STOKVEL SPECIFIC ===
    stokvel_contribution_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stokvel_contribution_frequency = models.CharField(max_length=50, blank=True, choices=[
        ('weekly', 'Weekly'),
        ('bi-weekly', 'Bi-Weekly'),
        ('monthly', 'Monthly'),
    ])
    stokvel_payout_type = models.CharField(max_length=50, blank=True, choices=[
        ('rotating', 'Rotating Payout'),
        ('lump_sum', 'Lump Sum at Year End'),
        ('emergency', 'Emergency Fund Pool'),
    ])
    stokvel_rotation_order = models.JSONField(null=True, blank=True, help_text="Array of member IDs in payout order")
    
    # === EMPLOYER UNION SPECIFIC ===
    employer_name = models.CharField(max_length=300, blank=True)
    employer_contact_person = models.CharField(max_length=200, blank=True)
    employer_contact_email = models.EmailField(blank=True)
    employer_contact_phone = models.CharField(max_length=20, blank=True)
    employer_verified = models.BooleanField(default=False)
    employer_verification_date = models.DateTimeField(null=True, blank=True)
    payroll_deduction_enabled = models.BooleanField(default=False)
    payroll_deduction_day = models.IntegerField(null=True, blank=True, help_text="Day of month")
    
    # === BURIAL SOCIETY SPECIFIC ===
    society_registration_number = models.CharField(max_length=100, blank=True)
    society_monthly_contribution = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    society_payout_per_funeral = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    society_elder_council = models.TextField(blank=True, help_text="Names of elder leaders")
    
    # === SAVINGS GROUP SPECIFIC ===
    savings_group_cycle_months = models.IntegerField(null=True, blank=True, help_text="Usually 12 months")
    savings_group_share_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    savings_group_max_shares_per_person = models.IntegerField(null=True, blank=True)
    savings_group_internal_lending_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Interest rate % for internal loans")
    savings_group_shareout_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"Settings for {self.group.name}"
 """



class GroupConstitution(models.Model):
    """
    Flexible constitution that adapts to different group types
    while respecting traditional rules
    """
    
    # Guarantee Structure
    GUARANTEE_TYPES = [
        ('equal', 'Equal Guarantee - All members guarantee equally'),
        ('tiered', 'Tiered Guarantee - Primary/Secondary split'),
        ('individual', 'Individual Only - Each guarantees own loans'),
        ('traditional', 'Traditional - Follows existing group rules'),
    ]

    group = models.OneToOneField(BorrowerGroup, on_delete=models.CASCADE, related_name='constitution', default="")
    
    guarantee_type = models.CharField(max_length=50, choices=GUARANTEE_TYPES, default='traditional')
    guarantee_percentage_per_member = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="% each member guarantees")
    
    # Decision Making
    decision_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=66.67, help_text="% approval needed for group decisions")
    loan_approval_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=75.00, help_text="% approval needed for member loans")
    admin_can_override = models.BooleanField(default=False)
    elder_approval_required = models.BooleanField(default=False, help_text="Requires elder/chief approval for large loans")
    
    # Member Obligations
    monthly_savings_required = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    meeting_attendance_required = models.IntegerField(default=75, help_text="% of meetings must attend")
    can_miss_consecutive_meetings = models.IntegerField(default=2)
    
    # Traditional Meeting Rules (respecting existing practices)
    physical_meetings_required = models.BooleanField(default=True, help_text="Group requires in-person meetings")
    meeting_frequency = models.CharField(max_length=50, default='monthly')
    fines_for_late_arrival = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fines_for_absence = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Default Handling (adapted to cultural context)
    grace_period_days = models.IntegerField(default=7)
    peer_support_activated = models.BooleanField(default=True, help_text="Group tries to help before penalties")
    collective_responsibility = models.BooleanField(default=True)
    traditional_mediation_first = models.BooleanField(default=True, help_text="Use chief/elders before formal action")
    
    # Membership Rules
    minimum_membership_months = models.IntegerField(default=6, help_text="Minimum time before can take loans")
    new_member_probation_months = models.IntegerField(default=3)
    exit_notice_period_days = models.IntegerField(default=30)
    leaving_member_must_clear_obligations = models.BooleanField(default=True)
    
    # Financial Rules
    maximum_loan_per_member = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    loan_amount_based_on_savings = models.BooleanField(default=False, help_text="Loan limited to 3x member savings")
    savings_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=3.0)
    
    # Cultural Provisions
    emergency_provisions = models.TextField(blank=True, help_text="Special rules for deaths, illness, etc.")
    seasonal_adjustments = models.TextField(blank=True, help_text="Rules for harvest season, school fees time, etc.")
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_amended = models.DateTimeField(auto_now=True)
    approved_by_members = models.BooleanField(default=False)
    approval_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Constitution for {self.group.name}"



class GroupMembership(models.Model):
    """
    Tracks individual membership in groups
    Respects traditional roles and hierarchies
    """
    
    ROLES = [
        ('admin', 'Administrator/Founder'),
        ('sub_admin', 'Sub-Administrator'),
        ('treasurer', 'Treasurer/Money Keeper'),
        ('secretary', 'Secretary/Record Keeper'),
        ('elder', 'Elder/Traditional Leader'),
        ('member', 'Regular Member'),
        ('probation', 'Probationary Member'),
    ]
    
    VERIFICATION_STATUS = [
        ('pending', 'Pending Verification'),
        ('identity_verified', 'Identity Verified'),
        ('reference_checked', 'References Checked'),
        ('community_vouched', 'Community Vouched'),
        ('fully_verified', 'Fully Verified'),
    ]
    
    group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE, related_name='memberships')
    borrower = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.CASCADE, related_name='group_memberships')
    
    # Role & Status
    role = models.CharField(max_length=50, choices=ROLES, default='member')
    status = models.CharField(max_length=50, default='active', choices=[
        ('pending', 'Pending Approval'),
        ('probation', 'Probationary Period'),
        ('active', 'Active Member'),
        ('suspended', 'Suspended'),
        ('exited', 'Left Group'),
    ])
    
    # Verification (crucial for trust)
    verification_status = models.CharField(max_length=50, choices=VERIFICATION_STATUS, default='pending')
    verified_by = models.ForeignKey('borrowers.BorrowerProfile', null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_members')
    verification_date = models.DateTimeField(null=True, blank=True)
    
    # Traditional Relationship Context
    relationship_to_admin = models.CharField(max_length=100, blank=True, help_text="Friend, Family, Neighbor, Colleague")
    years_known_admin = models.IntegerField(null=True, blank=True)
    same_village = models.BooleanField(default=False)
    
    # References (crucial in Lesotho context)
    reference_1_name = models.CharField(max_length=200, blank=True)
    reference_1_phone = models.CharField(max_length=20, blank=True)
    reference_1_relationship = models.CharField(max_length=100, blank=True)
    
    reference_2_name = models.CharField(max_length=200, blank=True)
    reference_2_phone = models.CharField(max_length=20, blank=True)
    reference_2_relationship = models.CharField(max_length=100, blank=True)
    
    # Traditional endorsements
    endorsed_by_chief = models.BooleanField(default=False)
    endorsed_by_group_members = models.ManyToManyField('borrowers.BorrowerProfile', related_name='member_endorsements', blank=True)
    endorsement_count = models.IntegerField(default=0)
    
    # Membership Timeline
    joined_date = models.DateTimeField(auto_now_add=True)
    probation_end_date = models.DateTimeField(null=True, blank=True)
    can_borrow_from = models.DateTimeField(null=True, blank=True, help_text="Date when can start taking loans")
    exit_date = models.DateTimeField(null=True, blank=True)

    # --- acting / temporary role support ---
    acting_until = models.DateTimeField(
        null=True, blank=True,
        help_text="If set, the current role is TEMPORARY and reverts to "
                  "previous_role after this time. Null = permanent role.",
    )
    previous_role = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Role to revert to when an acting role expires.",
    )
    
    # Participation Tracking
    meetings_attended = models.IntegerField(default=0)
    meetings_missed = models.IntegerField(default=0)
    consecutive_absences = models.IntegerField(default=0)
    
    # Financial Contribution (for stokvels, savings groups)
    total_savings_contributed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_savings_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Loan History within group
    loans_taken = models.IntegerField(default=0)
    loans_repaid_successfully = models.IntegerField(default=0)
    times_guaranteed_others = models.IntegerField(default=0)
    
    # Performance Score
    member_score = models.IntegerField(default=50, help_text="0-100 score based on participation and payment")
    
    class Meta:
        unique_together = ['group', 'borrower']
        ordering = ['-joined_date']
    
    def __str__(self):
        return f"{self.borrower.full_name} - {self.group.name} ({self.get_role_display()})"


class GroupInvitation(models.Model):
    """
    Invitation system for group admins to invite members
    Admin fills in member profile, invitee just sets username/password
    """
    group = models.ForeignKey('groups.BorrowerGroup', on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.CASCADE, related_name='invitations_sent')
    
    # Invitee profile - created by admin during invitation
    invitee = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.CASCADE, null=True, blank=True, related_name='received_invitations')
    
    # Invitee contact details (required for SMS/email)
    invitee_phone = models.CharField(max_length=20)
    invitee_email = models.EmailField(blank=True, null=True)
    invitee_name = models.CharField(max_length=200, help_text="Full name of invitee")
    
    # Invitation details
    invitation_code = models.CharField(max_length=20, unique=True, editable=False)
    personal_message = models.TextField(blank=True, help_text="Optional message to invitee")
    
    # Cultural context
    relationship = models.CharField(max_length=100, blank=True, help_text="Friend, Family, Colleague, etc.")
    reason_for_invite = models.TextField(blank=True, help_text="Why inviting this person")
    
    # Endorsements (optional feature for verification)
    endorsements_required = models.IntegerField(default=0, help_text="Number of members who must endorse")
    endorsed_by = models.ManyToManyField('borrowers.BorrowerProfile', related_name='endorsements_given', blank=True)
    
    # Status tracking
    status = models.CharField(max_length=50, default='pending', choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('withdrawn', 'Withdrawn by Inviter'),
    ])
    
    # Timestamps
    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Invitation expiry date")
    responded_at = models.DateTimeField(null=True, blank=True)
    
    # Communication tracking
    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "Group Invitation"
        verbose_name_plural = "Group Invitations"

    def save(self, *args, **kwargs):
        # Auto-generate invitation code if not exists
        if not self.invitation_code:
            self.invitation_code = uuid.uuid4().hex[:8].upper()
        
        # Set default expiry if not provided (30 days from now)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=30)
        
        super().save(*args, **kwargs)

    def get_activation_url(self):
        """Get the full activation URL for the invitation"""
        return reverse('groups:activate_invite', args=[self.invitation_code])
    
    def mark_accepted(self):
        """Mark invitation as accepted"""
        self.status = 'accepted'
        self.responded_at = timezone.now()
        self.save()
    
    def mark_declined(self):
        """Mark invitation as declined"""
        self.status = 'declined'
        self.responded_at = timezone.now()
        self.save()
    
    def is_expired(self):
        """Check if invitation has expired"""
        return self.expires_at < timezone.now() if self.expires_at else False
    
    def is_pending(self):
        """Check if invitation is still pending"""
        return self.status == 'pending' and not self.is_expired()
    
    def endorsements_met(self):
        """Check if required endorsements are met"""
        return self.endorsed_by.count() >= self.endorsements_required

    def __str__(self):
        return f"Invitation to {self.invitee_name or self.invitee_phone} for {self.group.name}"


class GroupActivity(models.Model):
    group = models.ForeignKey('groups.BorrowerGroup', on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} - {self.group.name}"


class GroupDocument(models.Model):
    group = models.ForeignKey('groups.BorrowerGroup', on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to='group_documents/')
    version = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.group.name} v{self.version} - {self.file.name}"


class GroupJoinRequest(models.Model):
    """
    Allow people to request to join existing groups
    Includes vetting process
    """
    group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE, related_name='join_requests')
    requester = models.ForeignKey('borrowers.BorrowerProfile', on_delete=models.CASCADE, related_name='group_requests')
    
    # Why joining?
    reason_for_joining = models.TextField()
    how_found_group = models.CharField(max_length=50, choices=[
        ('friend', 'Friend/Family in Group'),
        ('search', 'Searched on Platform'),
        ('recommended', 'Someone Recommended'),
        ('community', 'Community Leader Suggested'),
        ('workplace', 'Work at Same Place'),
        ('neighbor', 'Live in Same Area'),
    ])
    existing_connection = models.ForeignKey('borrowers.BorrowerProfile', null=True, blank=True, on_delete=models.SET_NULL, related_name='connection_referrals', help_text="Who in the group do you know?")
    
    # Vetting Process
    status = models.CharField(max_length=50, default='pending', choices=[
        ('pending', 'Pending Admin Review'),
        ('interview_scheduled', 'Interview Scheduled'),
        ('voting', 'Members Voting'),
        ('approved', 'Approved - Joining'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn by Requester'),
    ])
    
    # Member Voting
    approvals = models.ManyToManyField('borrowers.BorrowerProfile', related_name='join_request_approvals', blank=True)
    rejections = models.ManyToManyField('borrowers.BorrowerProfile', related_name='join_request_rejections', blank=True)
    approval_threshold_met = models.BooleanField(default=False)
    
    # Interview (traditional group practice)
    interview_scheduled_date = models.DateTimeField(null=True, blank=True)
    interviewed_by = models.ForeignKey('borrowers.BorrowerProfile', null=True, blank=True, on_delete=models.SET_NULL, related_name='interviews_conducted')
    interview_notes = models.TextField(blank=True)
    interview_completed = models.BooleanField(default=False)
    
    # Timeline
    requested_at = models.DateTimeField(auto_now_add=True)
    decision_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-requested_at']
    
    def __str__(self):
        return f"{self.requester.full_name} → {self.group.name}"


class GroupMeeting(models.Model):
    group = models.ForeignKey("BorrowerGroup", on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    # Optional meeting minutes text
    minutes = models.TextField(blank=True)

    # Optional uploaded minutes (PDF, DOCX, etc.)
    minutes_file = models.FileField(upload_to="group_meetings/minutes/", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.group.name}"
    

class MeetingAttendance(models.Model):
    meeting = models.ForeignKey(GroupMeeting, on_delete=models.CASCADE, related_name="attendance")
    member = models.ForeignKey("GroupMembership", on_delete=models.CASCADE)
    
    was_present = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("meeting", "member")


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ("member_added", "Member Added"),
        ("member_removed", "Member Removed"),
        ("member_promoted", "Member Promoted"),
        ("member_demoted", "Member Demoted"),

        ("role_changed", "Role Changed"),

        ("meeting_created", "Meeting Created"),
        ("meeting_updated", "Meeting Updated"),
        ("meeting_deleted", "Meeting Deleted"),

        ("document_uploaded", "Document Uploaded"),
        ("document_updated", "Document Updated"),
        ("document_deleted", "Document Deleted"),

        ("group_updated", "Group Updated"),
        ("group_created", "Group Created"),
    ]

    group = models.ForeignKey(
        "groups.BorrowerGroup",
        on_delete=models.CASCADE,
        related_name="activity_logs"
    )

    # The actor might not always exist (e.g., system automation)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities"
    )

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)

    # Optional text for more detailed info
    details = models.TextField(blank=True, default="")

    # Automatically set when log is created
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.group.name}"


class LenderGroupSubscription(models.Model):
    """
    Lenders subscribe to groups they want to work with
    More sophisticated than simple "interested" flag
    """
    
    SUBSCRIPTION_TYPES = [
        ('observer', 'Observer - Just Watching'),
        ('interested', 'Interested - Considering'),
        ('active', 'Active Lender - Currently Lending'),
        ('preferred', 'Preferred Partner - Long-term Relationship'),
        ('exclusive', 'Exclusive Partner - Only Lender'),
    ]
    
    lender = models.ForeignKey('lenders.LenderProfile', on_delete=models.CASCADE, related_name='group_subscriptions')
    group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE, related_name='lender_subscriptions')
    
    subscription_type = models.CharField(max_length=50, choices=SUBSCRIPTION_TYPES, default='interested')
    
    # Lender's Terms for this specific group
    max_loan_amount_per_member = models.DecimalField(max_digits=12, decimal_places=2, help_text="Maximum they'll lend to one member")
    max_total_exposure = models.DecimalField(max_digits=12, decimal_places=2, help_text="Maximum total outstanding to entire group")
    preferred_interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Special conditions for different group types
    requires_payroll_deduction = models.BooleanField(default=False, help_text="For employer unions")
    requires_stokvel_savings_first = models.BooleanField(default=False, help_text="For stokvels")
    respects_traditional_hierarchy = models.BooleanField(default=True)
    
    # Auto-approval settings
    auto_approve_under_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    auto_approve_for_top_performers = models.BooleanField(default=False)
    
    # Status
    subscribed_at = models.DateTimeField(auto_now_add=True)
    last_interaction = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Performance tracking
    loans_issued = models.IntegerField(default=0)
    total_amount_lent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    repayment_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ['lender', 'group']
        ordering = ['-subscribed_at']
    
    def __str__(self):
        return f"{self.lender.company_name} → {self.group.name} ({self.get_subscription_type_display()})"
    