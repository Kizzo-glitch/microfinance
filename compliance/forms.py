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



# ================================
# 2. UPDATE PROFILE FORM
# ================================

class ComplianceUpdateForm2(forms.ModelForm):
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
# 2. PERSONNEL PROFILE FORM
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



"""
class PersonnelProfileForm(forms.ModelForm):
    class Meta:
        model = PersonnelProfile
        fields = [
            # Identification
            'role',
            'full_name',
            'nationality',
            'country_of_residence',
            'date_of_birth',
            'place_of_birth',
            'id_or_passport_number',

            # Addresses
            'business_address',
            'residential_address',

            # Professional
            'professional_qualifications',
            'employment_history_10_years',

            # Affiliations
            'other_affiliations',
            'family_business_affiliations',

            # Declarations (booleans)
            'ever_disqualified',
            'legal_proceedings',
            'criminal_conviction',
            'bankruptcy',
            'dismissed_or_resigned',

            # Details (only shown if declaration is True — handled in UI)
            'disqualification_details',
            'legal_proceedings_details',
            'criminal_conviction_details',
            'bankruptcy_details',
            'dismissal_details',

            # Documents
            'police_clearance',
            'tax_clearance',
            'assets_liabilities_statement',
            'character_references',
            'bank_references',
            'id_copy',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'employment_history_10_years': forms.Textarea(attrs={'rows': 4}),
            'other_affiliations': forms.Textarea(attrs={'rows': 3}),
            'family_business_affiliations': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()

        # Validate that if a declaration is True, details must be provided
        declarations = [
            ('ever_disqualified', 'disqualification_details'),
            ('legal_proceedings', 'legal_proceedings_details'),
            ('criminal_conviction', 'criminal_conviction_details'),
            ('bankruptcy', 'bankruptcy_details'),
            ('dismissed_or_resigned', 'dismissal_details'),
        ]

        for decl_field, detail_field in declarations:
            if cleaned_data.get(decl_field) and not cleaned_data.get(detail_field):
                self.add_error(detail_field, 'Details are required when declaration is "Yes".')

        # Required documents (per Schedule III, Section 10)
        required_docs = {
            'police_clearance': 'Police Clearance',
            'tax_clearance': 'Tax Clearance',
            'assets_liabilities_statement': 'Certified Statement of Assets and Liabilities',
            'character_references': 'Two Notarized Character References',
            'bank_references': 'Two Bank Reference Letters',
            'id_copy': 'Certified ID/Passport Copy',
        }

        for field, label in required_docs.items():
            if not cleaned_data.get(field):
                self.add_error(field, f'{label} is mandatory per Schedule III.')

        return cleaned_data
"""

# ================================
# 3. PERSONNEL REGISTRATION FORM (Simplified for onboarding)
# (e.g., for lender to add their CEO, directors, etc.)
# ================================

class AddPersonnelForm(forms.ModelForm):
    class Meta:
        model = PersonnelProfile
        fields = ['role', 'full_name', 'nationality', 'date_of_birth', 'id_or_passport_number']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }