# forms.py

from django import forms
from django.core.validators import MinValueValidator, EmailValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import (
     ComplianceDocument,
     KeyPersonnel, CBLRegistration
    
)
from .models import LenderProfile



class ComplianceTierSelectionForm(forms.ModelForm):
    class Meta:
        model = CBLRegistration
        fields = ['target_tier', 'proposed_capital']

        widgets = {
            'target_tier': forms.RadioSelect,
            'proposed_capital': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 500000'
            })
        }

    def clean(self):
        cleaned = super().clean()
        tier = cleaned.get('target_tier')
        capital = cleaned.get('proposed_capital')

        if tier in ['tier1', 'tier2'] and (not capital or capital < 10000000):
            raise forms.ValidationError(
                "Tier 1 & 2 require minimum capital of M10,000,000"
            )

        if tier == 'tier3' and capital and capital < 500000:
            raise forms.ValidationError(
                "Tier 3 requires minimum capital of M500,000"
            )

        return cleaned


class ComplianceCompanyInfoForm(forms.ModelForm):
    class Meta:
        model = LenderProfile
        fields = [
            'company_name',
            'trading_name',
            'registration_number',
            'tax_identification_number',
            'date_of_establishment',
            'ownership_type',
            'physical_address',
            'city',
            'district',
        ]

        widgets = {
            'date_of_establishment': forms.DateInput(attrs={'type': 'date'}),
            'physical_address': forms.Textarea(attrs={'rows': 3}),
        }



class CapitalSourceForm(forms.ModelForm):
    class Meta:
        model = CBLRegistration
        fields = [
            'proposed_capital',
            'capital_source_explanation'
        ]

        widgets = {
            'capital_source_explanation': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Explain source of funds'
            })
        }



class GovernanceSetupForm(forms.ModelForm):
    class Meta:
        model = CBLRegistration
        fields = [
            'board_size',
            'has_audit_committee',
            'has_credit_committee',
            'has_risk_committee',
            'has_finance_manager',
            'has_compliance_officer',
        ]

    def clean_board_size(self):
        board_size = self.cleaned_data['board_size']
        if board_size < 3:
            raise forms.ValidationError("Minimum board size is 3")
        return board_size


class KeyPersonnelForm(forms.ModelForm):
    class Meta:
        model = KeyPersonnel
        exclude = ['registration', 'verified', 'verified_by']

        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
        }



class ComplianceDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ComplianceDocument
        fields = [
            'category',
            'document_type',
            'title',
            'file',
            'issue_date',
            'expiry_date',
            'reference_number',
        ]

        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class ComplianceReviewForm(forms.Form):
    confirm_accuracy = forms.BooleanField(
        label="I confirm all information is accurate"
    )
    agree_terms = forms.BooleanField(
        label="I agree to CBL compliance requirements"
    )


