from django import forms
from django.contrib.auth.forms import UserCreationForm
#from .models import BorrowerGroup
#from micro.models import User
from borrowers.models import BorrowerProfile
from django.contrib.auth import get_user_model

from .models import (
	BorrowerGroup,
	GroupConstitution,
	GroupTypeSpecificSettings,
	GroupJoinRequest,
	 GroupMembership,
	 GroupInvitation
)

User = get_user_model()


class BorrowerGroupRegistrationForm(UserCreationForm):
	first_name = forms.CharField(max_length=100)
	last_name = forms.CharField(max_length=100)
	email = forms.CharField(max_length=100)
	phone_number = forms.CharField(max_length=100)


	class Meta:
		model = User
		fields = ("username", 'first_name', 'last_name', 'email','phone_number', "password1", "password2")

	def save(self, commit=True):
		user = super().save(commit=False)
		user.save()
		# ✅ enforce role=borrower       
		BorrowerProfile.objects.get_or_create(user=user)
		return user



# -----------------------------
# GROUP CREATION & EDITING
# -----------------------------

class BorrowerGroupForm(forms.ModelForm):
	"""
	Form for creating or updating a borrower group such as a stokvel,
	employer union, or community savings group.
	"""
	class Meta:
		model = BorrowerGroup
		fields = [
			'name',
			'group_type',
			'description',
			'district',
			'community_council',
			'village',
			'established_year',
			'meeting_day',
			'meeting_location',
			'chief_endorsed',
			'chief_name',
			'chief_letter',
		]
		widgets = {
			'name': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'Enter group name (e.g., Maseru Women’s Savings Club)'
			}),
			'group_type': forms.Select(attrs={'class': 'form-select'}),
			'description': forms.Textarea(attrs={
				'class': 'form-control',
				'rows': 3,
				'placeholder': 'Briefly describe your group’s purpose and activities'
			}),
			'district': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'e.g., Maseru, Leribe'
			}),
			'community_council': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'Enter community council (optional)'
			}),
			'village': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'Enter village (optional)'
			}),
			'established_year': forms.NumberInput(attrs={
				'class': 'form-control',
				'placeholder': 'e.g., 2010'
			}),
			'meeting_day': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'e.g., Every Friday, or Last Sunday of each month'
			}),
			'meeting_location': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'Enter meeting location or chief’s kraal'
			}),
			'chief_endorsed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'chief_name': forms.TextInput(attrs={
				'class': 'form-control',
				'placeholder': 'Enter the name of the local chief if endorsed'
			}),
			'chief_letter': forms.ClearableFileInput(attrs={'class': 'form-control'}),
		}

	def clean(self):
		"""
		Custom validation for cultural endorsement fields.
		"""
		cleaned_data = super().clean()
		chief_endorsed = cleaned_data.get("chief_endorsed")
		chief_name = cleaned_data.get("chief_name")
		chief_letter = cleaned_data.get("chief_letter")

		if chief_endorsed and (not chief_name or not chief_letter):
			raise forms.ValidationError(
				"Please provide the chief’s name and upload a letter of endorsement."
			)

		return cleaned_data


# -----------------------------
# GROUP SPECIFIC SETTINGS
# -----------------------------

class GroupTypeSpecificSettingsForm(forms.ModelForm):
	"""
	Form for configuring type-specific group settings (Stokvel, Union, Burial, Savings)
	"""
	
	class Meta:
		model = GroupTypeSpecificSettings
		fields = [
			# General
			'group',

			# STOKVEL
			'stokvel_contribution_amount',
			'stokvel_contribution_frequency',
			'stokvel_payout_type',
			'stokvel_rotation_order',

			# EMPLOYER UNION
			'employer_name',
			'employer_contact_person',
			'employer_contact_email',
			'employer_contact_phone',
			'employer_verified',
			'employer_verification_date',
			'payroll_deduction_enabled',
			'payroll_deduction_day',

			# BURIAL SOCIETY
			'society_registration_number',
			'society_monthly_contribution',
			'society_payout_per_funeral',
			'society_elder_council',

			# SAVINGS GROUP
			'savings_group_cycle_months',
			'savings_group_share_value',
			'savings_group_max_shares_per_person',
			'savings_group_internal_lending_rate',
			'savings_group_shareout_date',
		]

		widgets = {
			# --- STOKVEL ---
			'stokvel_contribution_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter contribution amount'}),
			'stokvel_contribution_frequency': forms.Select(attrs={'class': 'form-select'}),
			'stokvel_payout_type': forms.Select(attrs={'class': 'form-select'}),
			'stokvel_rotation_order': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'e.g. [1, 5, 3, 2]'}),

			# --- EMPLOYER UNION ---
			'employer_name': forms.TextInput(attrs={'class': 'form-control'}),
			'employer_contact_person': forms.TextInput(attrs={'class': 'form-control'}),
			'employer_contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
			'employer_contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
			'employer_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'employer_verification_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
			'payroll_deduction_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'payroll_deduction_day': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 25'}),

			# --- BURIAL SOCIETY ---
			'society_registration_number': forms.TextInput(attrs={'class': 'form-control'}),
			'society_monthly_contribution': forms.NumberInput(attrs={'class': 'form-control'}),
			'society_payout_per_funeral': forms.NumberInput(attrs={'class': 'form-control'}),
			'society_elder_council': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'List elder names'}),

			# --- SAVINGS GROUP ---
			'savings_group_cycle_months': forms.NumberInput(attrs={'class': 'form-control'}),
			'savings_group_share_value': forms.NumberInput(attrs={'class': 'form-control'}),
			'savings_group_max_shares_per_person': forms.NumberInput(attrs={'class': 'form-control'}),
			'savings_group_internal_lending_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '%'}),
			'savings_group_shareout_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
		}
	
	
	def __init__(self, *args, **kwargs):
		# ✅ Extract group_type safely (if provided)
		group_type = kwargs.pop('group_type', None)
		super().__init__(*args, **kwargs)

		# ✅ Hide irrelevant fields based on group type
		if group_type == 'stokvel':
			self.fields_to_keep([
				'stokvel_contribution_amount',
				'stokvel_contribution_frequency',
				'stokvel_payout_type',
				'stokvel_rotation_order'
			])
		elif group_type == 'employer_union':
			self.fields_to_keep([
				'employer_name',
				'employer_contact_person',
				'employer_contact_email',
				'employer_contact_phone',
				'payroll_deduction_enabled',
				'payroll_deduction_day'
			])
		elif group_type == 'burial_society':
			self.fields_to_keep([
				'society_registration_number',
				'society_monthly_contribution',
				'society_payout_per_funeral',
				'society_elder_council'
			])
		elif group_type == 'savings_group':
			self.fields_to_keep([
				'savings_group_cycle_months',
				'savings_group_share_value',
				'savings_group_max_shares_per_person',
				'savings_group_internal_lending_rate',
				'savings_group_shareout_date'
			])
		else:
			# Default: show all fields
			pass

	def fields_to_keep(self, allowed):
		#Helper: removes all fields except those listed.
		for field_name in list(self.fields.keys()):
			if field_name not in allowed:
				del self.fields[field_name]


# -----------------------------
# GROUP CONSTITUTION FORM
# -----------------------------

class GroupConstitutionForm(forms.ModelForm):
	class Meta:
		model = GroupConstitution
		fields = [
			# Guarantee Structure
			'guarantee_type', 'guarantee_percentage_per_member',

			# Decision Making
			'decision_threshold', 'loan_approval_threshold',
			'admin_can_override', 'elder_approval_required',

			# Member Obligations
			'monthly_savings_required', 'meeting_attendance_required',
			'can_miss_consecutive_meetings',

			# Traditional Meeting Rules
			'physical_meetings_required', 'meeting_frequency',
			'fines_for_late_arrival', 'fines_for_absence',

			# Default Handling
			'grace_period_days', 'peer_support_activated',
			'collective_responsibility', 'traditional_mediation_first',

			# Membership Rules
			'minimum_membership_months', 'new_member_probation_months',
			'exit_notice_period_days', 'leaving_member_must_clear_obligations',

			# Financial Rules
			'maximum_loan_per_member', 'loan_amount_based_on_savings',
			'savings_multiplier',

			# Cultural Provisions
			'emergency_provisions', 'seasonal_adjustments',

			# Approval
			'approved_by_members', 'approval_date',
		]

		widgets = {
			# Guarantee
			'guarantee_type': forms.Select(attrs={'class': 'form-select'}),
			'guarantee_percentage_per_member': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 25.00'}),

			# Decision Making
			'decision_threshold': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 66.67'}),
			'loan_approval_threshold': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 75.00'}),
			'admin_can_override': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'elder_approval_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# Member Obligations
			'monthly_savings_required': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 200.00'}),
			'meeting_attendance_required': forms.NumberInput(attrs={'class': 'form-control'}),
			'can_miss_consecutive_meetings': forms.NumberInput(attrs={'class': 'form-control'}),

			# Traditional Meeting Rules
			'physical_meetings_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'meeting_frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. monthly'}),
			'fines_for_late_arrival': forms.NumberInput(attrs={'class': 'form-control'}),
			'fines_for_absence': forms.NumberInput(attrs={'class': 'form-control'}),

			# Default Handling
			'grace_period_days': forms.NumberInput(attrs={'class': 'form-control'}),
			'peer_support_activated': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'collective_responsibility': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'traditional_mediation_first': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# Membership Rules
			'minimum_membership_months': forms.NumberInput(attrs={'class': 'form-control'}),
			'new_member_probation_months': forms.NumberInput(attrs={'class': 'form-control'}),
			'exit_notice_period_days': forms.NumberInput(attrs={'class': 'form-control'}),
			'leaving_member_must_clear_obligations': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# Financial Rules
			'maximum_loan_per_member': forms.NumberInput(attrs={'class': 'form-control'}),
			'loan_amount_based_on_savings': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'savings_multiplier': forms.NumberInput(attrs={'class': 'form-control'}),

			# Cultural
			'emergency_provisions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
			'seasonal_adjustments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),

			# Approval
			'approved_by_members': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'approval_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
		}

		labels = {
			'guarantee_type': 'Guarantee Type',
			'guarantee_percentage_per_member': 'Guarantee (%) Per Member',
			'decision_threshold': 'Decision Approval Threshold (%)',
			'loan_approval_threshold': 'Loan Approval Threshold (%)',
			'monthly_savings_required': 'Monthly Savings (ZAR)',
			'meeting_attendance_required': 'Required Attendance (%)',
			'can_miss_consecutive_meetings': 'Max Consecutive Missed Meetings',
			'meeting_frequency': 'Meeting Frequency',
			'fines_for_late_arrival': 'Fine for Late Arrival (ZAR)',
			'fines_for_absence': 'Fine for Absence (ZAR)',
			'grace_period_days': 'Grace Period (Days)',
			'minimum_membership_months': 'Min Membership (Months)',
			'new_member_probation_months': 'Probation Period (Months)',
			'exit_notice_period_days': 'Exit Notice (Days)',
			'maximum_loan_per_member': 'Max Loan Per Member (ZAR)',
			'savings_multiplier': 'Savings Multiplier (x)',
			'emergency_provisions': 'Emergency Provisions',
			'seasonal_adjustments': 'Seasonal Adjustments',
			'approval_date': 'Member Approval Date',
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for name, field in self.fields.items():
			if isinstance(field.widget, forms.CheckboxInput):
				field.widget.attrs.update({'class': 'form-check-input me-2'})
			else:
				field.widget.attrs.update({'class': 'form-control'})


"""class GroupConstitutionForm(forms.ModelForm):
	class Meta:
		model = GroupConstitution
		fields = [
			'objectives',
			'rules',
			'membership_criteria',
			'meeting_frequency',
			'dispute_resolution_mechanism',
			'uploaded_file',
		]
		widgets = {
			'objectives': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
			'rules': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
			'membership_criteria': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
			'meeting_frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Monthly, Weekly'}),
			'dispute_resolution_mechanism': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
			'uploaded_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
		}"""


# -----------------------------
# GROUP MEMBERSHIP
# -----------------------------

class GroupMembershipForm(forms.ModelForm):
	class Meta:
		model = GroupMembership
		fields = [
			# Core Links
			'group', 'borrower',

			# Roles & Status
			'role', 'status',

			# Verification
			'verification_status', 'verified_by', 'verification_date',

			# Relationship Context
			'relationship_to_admin', 'years_known_admin', 'same_village',

			# References
			'reference_1_name', 'reference_1_phone', 'reference_1_relationship',
			'reference_2_name', 'reference_2_phone', 'reference_2_relationship',

			# Traditional Endorsements
			'endorsed_by_chief', 'endorsed_by_group_members', 'endorsement_count',

			# Membership Timeline
			#'joined_date'
				'probation_end_date', 'can_borrow_from', 'exit_date',

			# Participation Tracking
			'meetings_attended', 'meetings_missed', 'consecutive_absences',

			# Financial Contribution
			'total_savings_contributed', 'current_savings_balance',

			# Loan History
			'loans_taken', 'loans_repaid_successfully', 'times_guaranteed_others',

			# Performance Score
			'member_score',
		]

		widgets = {
			# Core links
			'group': forms.Select(attrs={'class': 'form-select'}),
			'borrower': forms.Select(attrs={'class': 'form-select'}),

			# Roles
			'role': forms.Select(attrs={'class': 'form-select'}),
			'status': forms.Select(attrs={'class': 'form-select'}),

			# Verification
			'verification_status': forms.Select(attrs={'class': 'form-select'}),
			'verified_by': forms.Select(attrs={'class': 'form-select'}),
			'verification_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),

			# Relationship Context
			'relationship_to_admin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Friend, Colleague'}),
			'years_known_admin': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
			'same_village': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# References
			'reference_1_name': forms.TextInput(attrs={'class': 'form-control'}),
			'reference_1_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+266...'}),
			'reference_1_relationship': forms.TextInput(attrs={'class': 'form-control'}),
			'reference_2_name': forms.TextInput(attrs={'class': 'form-control'}),
			'reference_2_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+266...'}),
			'reference_2_relationship': forms.TextInput(attrs={'class': 'form-control'}),

			# Traditional Endorsements
			'endorsed_by_chief': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'endorsed_by_group_members': forms.SelectMultiple(attrs={'class': 'form-select'}),
			'endorsement_count': forms.NumberInput(attrs={'class': 'form-control'}),

			# Membership Timeline
			#'joined_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
			'probation_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
			'can_borrow_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
			'exit_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),

			# Participation Tracking
			'meetings_attended': forms.NumberInput(attrs={'class': 'form-control'}),
			'meetings_missed': forms.NumberInput(attrs={'class': 'form-control'}),
			'consecutive_absences': forms.NumberInput(attrs={'class': 'form-control'}),

			# Financial Contribution
			'total_savings_contributed': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
			'current_savings_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),

			# Loan History
			'loans_taken': forms.NumberInput(attrs={'class': 'form-control'}),
			'loans_repaid_successfully': forms.NumberInput(attrs={'class': 'form-control'}),
			'times_guaranteed_others': forms.NumberInput(attrs={'class': 'form-control'}),

			# Performance Score
			'member_score': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
		}

		labels = {
			'group': 'Group Name',
			'borrower': 'Member',
			'role': 'Role in Group',
			'status': 'Membership Status',
			'verification_status': 'Verification Level',
			'verified_by': 'Verified By',
			'verification_date': 'Date Verified',
			'relationship_to_admin': 'Relationship to Group Admin',
			'years_known_admin': 'Years Known Admin',
			'same_village': 'Same Village',
			'reference_1_name': 'Reference 1 - Name',
			'reference_1_phone': 'Reference 1 - Phone',
			'reference_1_relationship': 'Reference 1 - Relationship',
			'reference_2_name': 'Reference 2 - Name',
			'reference_2_phone': 'Reference 2 - Phone',
			'reference_2_relationship': 'Reference 2 - Relationship',
			'endorsed_by_chief': 'Endorsed by Chief',
			'endorsed_by_group_members': 'Endorsed by Group Members',
			'endorsement_count': 'Total Endorsements',
			#'joined_date': 'Join Date',
			'probation_end_date': 'Probation End Date',
			'can_borrow_from': 'Eligible to Borrow From',
			'exit_date': 'Exit Date',
			'meetings_attended': 'Meetings Attended',
			'meetings_missed': 'Meetings Missed',
			'consecutive_absences': 'Consecutive Absences',
			'total_savings_contributed': 'Total Savings Contributed',
			'current_savings_balance': 'Current Savings Balance',
			'loans_taken': 'Loans Taken',
			'loans_repaid_successfully': 'Loans Repaid Successfully',
			'times_guaranteed_others': 'Times Guaranteed Others',
			'member_score': 'Member Score (0–100)',
		}

# -----------------------------
# GROUP INVITES B-PROFILE
# -----------------------------

class BorrowerMiniForm(forms.ModelForm):
	"""
	A lightweight borrower form used when the invitee doesn't yet exist.
	"""
	class Meta:
		model = BorrowerProfile
		fields = '__all__'
		exclude = [
			'user',
		]

		""" 
		
		['first_name', 'last_name', 'email', 'phone_number', 'id_number', 'employment_type']
		widgets = {
			'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
			'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
			'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com'}),
			'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+266...'}),
			'id_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ID or Passport No.'}),
			'employment_type': forms.Select(attrs={'class': 'form-select'}),
		}
		"""

# -----------------------------
# GROUP INVITES
# -----------------------------

class GroupInvitationForm(forms.ModelForm):
	borrower_profile = BorrowerMiniForm()

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields['invitee'].widget.attrs.update({'class': 'form-select', 'id': 'invitee-select'})

		
	class Meta:
		model = GroupInvitation
		fields = [
			# Basic links
			'group', 
			'invited_by', 'invitee', 
			'invitee_name', 'invitee_phone', 'invitee_email',

			# Invitation details
			'personal_message',

			# Cultural and contextual
			'relationship', 'reason_for_invite',

			# Endorsements
			'endorsements_required', 'endorsed_by',

			# Status and lifecycle
			#'status', 
			'expires_at',
		]
		exclude = [
			'invitation_code',
			
			#'invited_by',
			#'group',
			'status',
			'sent_at',
			'responded_at',
			'sms_sent',
			'sms_sent_at',
			'endorsed_by',
		]

		widgets = {
			# Group and Inviter
			'group': forms.Select(attrs={'class': 'form-select'}),
			'invited_by': forms.Select(attrs={'class': 'form-select'}),
			'invitee': forms.Select(attrs={'class': 'form-select'}),
			
			# Invitee details
			'invitee_name': forms.TextInput(attrs={
				'class': 'form-control', 
				'placeholder': 'Name of invitee (if not registered yet)'
			}),
			'invitee_phone': forms.TextInput(attrs={
				'class': 'form-control', 
				'placeholder': '+266...'
			}),

			'personal_message': forms.Textarea(attrs={
				'class': 'form-control', 
				'rows': 3, 
				'placeholder': 'Optional personal message to the invitee...'
			}),

			# Cultural context
			'relationship': forms.TextInput(attrs={
				'class': 'form-control', 
				'placeholder': 'Friend, colleague, relative...'
			}),
			'reason_for_invite': forms.Textarea(attrs={
				'class': 'form-control', 
				'rows': 2, 
				'placeholder': 'Why are you inviting this person to join the group?'
			}),

			# Endorsements
			'endorsements_required': forms.NumberInput(attrs={
				'class': 'form-control', 
				'min': 0
			}),
			'endorsed_by': forms.SelectMultiple(attrs={
				'class': 'form-select'
			}),

			# Status
			'status': forms.Select(attrs={'class': 'form-select'}),
			'expires_at': forms.DateInput(attrs={
				'class': 'form-control', 
				'type': 'date'
			}),
		}

		labels = {
			'group': 'Group',
			'invited_by': 'Invited By',
			'invitee': 'Invitee (if already registered)',
			'invitee_name': 'Invitee Name',
			'invitee_phone': 'Invitee Phone Number',			
			'personal_message': 'Personal Message',
			'relationship': 'Relationship to Invitee',
			'reason_for_invite': 'Reason for Invitation',
			'endorsements_required': 'Number of Endorsements Required',
			'endorsed_by': 'Endorsed By',
			'status': 'Invitation Status',
			'expires_at': 'Expiry Date',
		}


class ActivationForm(UserCreationForm):
	email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))

	class Meta:
		model = User
		fields = ("username","phone_number" ,"email", "password1", "password2")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for fieldname, field in self.fields.items():
			# add bootstrap classes
			if not getattr(field.widget, 'attrs', None):
				field.widget.attrs = {}
			if 'class' not in field.widget.attrs:
				field.widget.attrs['class'] = 'form-control'



# -----------------------------
# JOIN REQUEST FORM
# -----------------------------

class GroupJoinRequestForm(forms.ModelForm):
	class Meta:
		model = GroupJoinRequest
		fields = [
			# Basic info
			'requester', 'reason_for_joining', 'how_found_group', 'existing_connection',

			# Vetting process
			'status', 'approvals', 'rejections', 'approval_threshold_met',

			# Interview details
			'interview_scheduled_date', 'interviewed_by', 'interview_notes', 'interview_completed',

			# Decision metadata
			'decision_date', 'rejection_reason',
		]

		exclude = [
			'group',
			
		]

		widgets = {
			# Group and Requester
			'group': forms.Select(attrs={'class': 'form-select'}),
			'requester': forms.Select(attrs={'class': 'form-select'}),

			# Application details
			'reason_for_joining': forms.Textarea(attrs={
				'class': 'form-control',
				'rows': 3,
				'placeholder': 'Briefly explain why you wish to join this group...'
			}),
			'how_found_group': forms.Select(attrs={'class': 'form-select'}),
			'existing_connection': forms.Select(attrs={
				'class': 'form-select',
				'help_text': 'If you know anyone in the group, select their name here'
			}),

			# Vetting process
			'status': forms.Select(attrs={'class': 'form-select'}),
			'approvals': forms.SelectMultiple(attrs={'class': 'form-select'}),
			'rejections': forms.SelectMultiple(attrs={'class': 'form-select'}),
			'approval_threshold_met': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# Interview details
			'interview_scheduled_date': forms.DateTimeInput(attrs={
				'class': 'form-control',
				'type': 'datetime-local'
			}),
			'interviewed_by': forms.Select(attrs={'class': 'form-select'}),
			'interview_notes': forms.Textarea(attrs={
				'class': 'form-control',
				'rows': 3,
				'placeholder': 'Enter notes from the group interview (if conducted)'
			}),
			'interview_completed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

			# Decision
			'decision_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
			'rejection_reason': forms.Textarea(attrs={
				'class': 'form-control',
				'rows': 2,
				'placeholder': 'If rejected, provide a reason...'
			}),
		}

		labels = {
			'group': 'Group',
			'requester': 'Requester (Borrower)',
			'reason_for_joining': 'Why do you want to join?',
			'how_found_group': 'How did you find this group?',
			'existing_connection': 'Existing Connection (if any)',
			'status': 'Request Status',
			'approvals': 'Members Who Approved',
			'rejections': 'Members Who Rejected',
			'approval_threshold_met': 'Approval Threshold Met',
			'interview_scheduled_date': 'Interview Date & Time',
			'interviewed_by': 'Interview Conducted By',
			'interview_notes': 'Interview Notes',
			'interview_completed': 'Interview Completed?',
			'decision_date': 'Decision Date',
			'rejection_reason': 'Rejection Reason (if applicable)',
		}



# -------------------------------------------
# 1️⃣ Borrower Form – Simple Join Request
# -------------------------------------------
class BorrowerJoinRequestForm(forms.ModelForm):
	class Meta:
		model = GroupJoinRequest
		fields = [
			'reason_for_joining',
			'how_found_group',
			'existing_connection',
		]
		exclude = [
			'group',
			'requester',
			'status'
		]
	
		widgets = {
			'group': forms.Select(attrs={'class': 'form-select'}),
			'reason_for_joining': forms.Textarea(attrs={
				'class': 'form-control',
				'rows': 3,
				'placeholder': 'Briefly explain why you wish to join this group...'
			}),
			'how_found_group': forms.Select(attrs={'class': 'form-select'}),
			'existing_connection': forms.Select(attrs={'class': 'form-select'}),
		}

		labels = {
			'group': 'Select Group',
			'reason_for_joining': 'Why do you want to join?',
			'how_found_group': 'How did you find this group?',
			'existing_connection': 'Do you know anyone in the group?',
		}

	def save(self, commit=True):
		"""
		Automatically sets status to 'pending' and handles requester in the view
		"""
		instance = super().save(commit=False)
		instance.status = 'pending'
		if commit:
			instance.save()
		return instance




# -------------------------------------------
# 2️⃣ Group Admin / Leader Review Form
# -------------------------------------------
class GroupAdminReviewForm(forms.ModelForm):
	class Meta:
		model = GroupJoinRequest
		fields = [
			'status',
			'approvals',
			'rejections',
			'approval_threshold_met',
			'interview_scheduled_date',
			'interviewed_by',
			'interview_notes',
			'interview_completed',
			'decision_date',
			'rejection_reason',
		]

		widgets = {
			'status': forms.Select(attrs={'class': 'form-select'}),
			'approvals': forms.SelectMultiple(attrs={'class': 'form-select'}),
			'rejections': forms.SelectMultiple(attrs={'class': 'form-select'}),
			'approval_threshold_met': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'interview_scheduled_date': forms.DateTimeInput(attrs={
				'class': 'form-control', 'type': 'datetime-local'
			}),
			'interviewed_by': forms.Select(attrs={'class': 'form-select'}),
			'interview_notes': forms.Textarea(attrs={
				'class': 'form-control', 'rows': 3, 'placeholder': 'Notes from the group interview...'
			}),
			'interview_completed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
			'decision_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
			'rejection_reason': forms.Textarea(attrs={
				'class': 'form-control', 'rows': 2, 'placeholder': 'If rejected, provide a reason...'
			}),
		}

		labels = {
			'status': 'Current Status',
			'approvals': 'Members Who Approved',
			'rejections': 'Members Who Rejected',
			'approval_threshold_met': 'Approval Threshold Met',
			'interview_scheduled_date': 'Interview Date & Time',
			'interviewed_by': 'Interview Conducted By',
			'interview_notes': 'Interview Notes',
			'interview_completed': 'Interview Completed?',
			'decision_date': 'Decision Date',
			'rejection_reason': 'Rejection Reason',
		}



