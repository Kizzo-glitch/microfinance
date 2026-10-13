from django import forms
from django.core.exceptions import ValidationError

from compliance.compliace_services import ComplianceDashboardService
from .models import ComplianceProfile, PersonnelProfile


# ================================
# 1. INSTITUTIONAL COMPLIANCE FORM
# (Maps to Schedule I, Schedule II, and Checklist)
# ================================


class ComplianceProfileForm(forms.ModelForm):
    class Meta:
        model = ComplianceProfile
        fields = [
            # Application metadata
            'cbl_application_reference',
            
            # Core documents
            'schedule_i',
            'schedule_ii',
            'business_plan',
            'audited_financials',
            'financial_statements_certified',
            'capital_commitment_letter',
            'bank_statements_capital',
            'tax_clearance_institution',
            'memorandum_articles',
            'home_supervisor_consent',

            # Policies
            'risk_management_manual',
            'aml_cft_manual',
            'complaints_procedure',

            # Governance
            'board_resolution_for_licensing',
            'memorandum_articles',
            'board_list_with_terms',
            'credit_committee_terms',
            'internal_audit_charter',

            # Fees
            'investigation_fee_paid',
            'registration_fee_paid',

            # Notes
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        self.lender = kwargs.pop('lender', None)
        super().__init__(*args, **kwargs)
        if not self.lender:
            raise ValueError("Lender instance is required")

        # Dynamically hide fields based on tier
        tier = self.lender.cbl_tier

        # Tier 3 does NOT need business plan, audited financials, or certain governance docs
        if tier == 'tier3':
            for field in ['business_plan', 'audited_financials', 'credit_committee_terms', 'internal_audit_charter']:
                if field in self.fields:
                    del self.fields[field]

        # Tier 1/2 need risk manual; Tier 3 does not (per Checklist)
        if tier == 'tier3':
            del self.fields['risk_management_manual']

        # Foreign institutions need home supervisor consent
        # (Assume lender.is_foreign flag exists — if not, you may add it to LenderProfile)
        # For now, we keep it visible but optional

    def clean(self):
        cleaned_data = super().clean()
        tier = self.lender.cbl_tier

        # Tier 1 & 2: business plan required
        if tier in ['tier1', 'tier2']:
            if not cleaned_data.get('business_plan'):
                self.add_error('business_plan', 'Business plan is required for Tier 1 and Tier 2.')

        # Tier 1 & 2: audited financials (if existing institution)
        # We assume startup vs. existing is handled externally; make optional but warn if missing
        # Tier 3: certified financials required
        if tier == 'tier3':
            if not cleaned_data.get('financial_statements_certified'):
                self.add_error('financial_statements_certified', 'Certified financial statements (by accountant) are required for Tier 3.')

        # All tiers: AML, complaints, tax clearance required
        required_docs = {
            'aml_cft_manual': 'AML/CFT Manual',
            'complaints_procedure': 'Consumer Complaints Procedure',
            'tax_clearance_institution': 'Institution Tax Clearance',
        }
        for field, label in required_docs.items():
            if not cleaned_data.get(field):
                self.add_error(field, f'{label} is required for all tiers.')

        return cleaned_data



# ---------------------------------------------------------------------------
# 2 — the Registered Lender's license submission form (the CLAIM)
# ---------------------------------------------------------------------------
 
class LicenseSubmissionForm(forms.ModelForm):
    """
    What a licensed lender fills in to submit their EXISTING CBL licence for
    platform verification. Only the claim + evidence fields — never the
    authoritative fields, never the verification state.
    """
 
    class Meta:
        model = ComplianceProfile   
        fields = [
            'submitted_license_number',
            'submitted_license_expiry',
            'license_certificate',
        ]
        widgets = {
            'submitted_license_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. MFI/2024/0137',
            }),
            'submitted_license_expiry': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'license_certificate': forms.ClearableFileInput(attrs={
                'class': 'form-control-file',
                'accept': 'image/*,application/pdf',
            }),
        }
        labels = {
            'submitted_license_number': 'Your CBL licence number',
            'submitted_license_expiry': 'Licence expiry date',
            'license_certificate': 'Upload your licence certificate',
        }
        help_texts = {
            'submitted_license_number':
                'Enter the licence number exactly as it appears on your '
                'certificate from the Central Bank of Lesotho.',
            'license_certificate':
                'A clear scan or photo of your CBL licence. This is seen only '
                'by our verification team, never by borrowers.',
        }
 
    def clean(self):
        cleaned = super().clean()
        number = cleaned.get('submitted_license_number')
        # On a fresh submission we need the certificate as evidence. On a
        # re-submission the instance may already carry one, so only insist
        # when there is a number but no certificate anywhere.
        has_cert = cleaned.get('license_certificate') or getattr(
            self.instance, 'license_certificate', None)
        if number and not has_cert:
            self.add_error(
                'license_certificate',
                'Please upload your licence certificate so our team can '
                'verify the number against the CBL register.')
        if not number:
            self.add_error(
                'submitted_license_number',
                'Enter your CBL licence number.')
        return cleaned


    
# ================================
# 3. UPDATE PROFILE FORM
# ================================

class ComplianceUpdateForm(forms.ModelForm):
    class Meta:
        model = ComplianceProfile
        # List all possible upload fields
        fields = [
            'schedule_i', 'schedule_ii', 'tax_clearance_institution',
            'business_plan', 'audited_financials', 'financial_statements_certified',
            'capital_commitment_letter', 'bank_statements_capital',
            'risk_management_manual', 'aml_cft_manual', 'complaints_procedure',
            'memorandum_articles', 'board_resolution_for_licensing',
            'board_list_with_terms', 'credit_committee_terms', 'internal_audit_charter'
        ]

    def __init__(self, *args, lender=None, **kwargs):
        super().__init__(*args, **kwargs)
        if lender:
            # Determine which fields to show for this tier
            service = ComplianceDashboardService(lender)
            required_fields = service._get_required_docs()

            # Remove fields not required for this tier
            for field_name in list(self.fields.keys()):
                if field_name not in required_fields:
                    self.fields.pop(field_name)




# ================================
# 4. PERSONNEL PROFILE FORM
# (Maps 1:1 to Fit & Proper Questionnaire + Schedule III)
# ================================

class PersonnelProfileForm(forms.ModelForm):
    class Meta:
        model = PersonnelProfile
        exclude = ['lender', 'fit_proper_questionnaire_submitted', 'schedule_iii_submitted']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'occupation_history': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Summarize your last 10 years...'}),
            'employment_history_10_years': forms.Textarea(attrs={'rows': 4}),
            'disqualification_details': forms.Textarea(attrs={'rows': 2}),
            'legal_proceedings_details': forms.Textarea(attrs={'rows': 2}),
            'criminal_conviction_details': forms.Textarea(attrs={'rows': 2}),
            'bankruptcy_details': forms.Textarea(attrs={'rows': 2}),
            'dismissal_details': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap classes to all fields
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
        
        # Checkbox specific styling
        checkbox_fields = [
            'ever_disqualified', 'legal_proceedings', 
            'criminal_conviction', 'bankruptcy', 'dismissed_or_resigned'
        ]
        for field_name in checkbox_fields:
            self.fields[field_name].widget.attrs.update({'class': 'form-check-input'})




# ================================
#  PERSONNEL REGISTRATION FORM (Simplified for onboarding)
# (e.g., for lender to add their CEO, directors, etc.)
# ================================

class AddPersonnelForm(forms.ModelForm):
    class Meta:
        model = PersonnelProfile
        fields = ['role', 'full_name', 'nationality', 'date_of_birth', 'id_or_passport_number']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }