from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ObjectDoesNotExist

from django.forms import inlineformset_factory

from .models import LenderProfile, LenderDocs, LenderProduct, ProductFee
from loans.models import LoanApplication, Loan

from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal




# ---------------------------------------------------------------------------
# CBL licence check - form mixin that enforces the lock
# ---------------------------------------------------------------------------

def _compliance_of(lender):
    """
    Safely return a lender's ComplianceProfile, or None if it doesn't exist yet.
 
    lender.compliance is a reverse OneToOne: when no row exists it RAISES
    RelatedObjectDoesNotExist (a subclass of ObjectDoesNotExist), it does NOT
    return None — so getattr(lender, 'compliance', None) would still raise.
    This is the one correct way to read it.
    """
    try:
        return lender.compliance
    except ObjectDoesNotExist:
        return None



class CblStatusLockMixin:
    """
    Mix into the lender profile form. Locks cbl_license_status to
    'already_licensed' once the licence is verified — disables the field and
    rejects any attempt to change it via a tampered POST.
    """
 
    def _license_is_verified(self):
        lender = getattr(self.instance, 'pk', None) and self.instance
        if not lender:
            return False
        cp = _compliance_of(lender)
        return bool(cp and cp.license_verification_state == 'verified')
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'cbl_license_status' in self.fields and self._license_is_verified():
            f = self.fields['cbl_license_status']
            f.disabled = True            # Django ignores POSTed value for disabled fields
            f.help_text = ("Your CBL licence is verified, so this is locked to "
                           "'already licensed'.")
 
    def clean_cbl_license_status(self):
        value = self.cleaned_data.get('cbl_license_status')
        # Belt-and-braces: even if the disabled attr were bypassed, hold the lock.
        if self._license_is_verified():
            return 'already_licensed'
        return value
 



class LenderInfoForm(CblStatusLockMixin, forms.ModelForm):
	
	# 1. CORE COMPANY INFO (FIXED: registration_no -> registration_number)
	company_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Company Name'}), required=True)
	trading_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Trading Name (Optional)'}), required=False) # New
	registration_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Registration Number'}), required=False) # Changed to match model
	tax_identification_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Tax Identification Number (TIN)'}), required=False) # Changed to match model

	# 2. CONTACT & ADDRESS (FIXED: business_email_ddress -> business_email, office_address -> physical_address)
	business_email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Business Email Address'}), required=True) # Changed to match model
	phone_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Primary Phone Number'}), required=True)
	alternate_phone = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Alternate Phone (Optional)'}), required=False) # New
	website = forms.URLField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Website URL (Optional)'}), required=False) # New
	physical_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Physical Office Address'}), required=True) # Changed to match model
	city = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'City'}), required=True) # New
	district = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'District (Optional)'}), required=False) # New
	postal_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Postal Address (Optional)'}), required=False) # New

	# 3. LEADERSHIP
	ceo_first_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO First Name'}), required=True)
	ceo_last_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO Last Name'}), required=True)
	ceo_email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO Email (Optional)'}), required=False) # New
	ceo_phone = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO Phone (Optional)'}), required=False) # New

	# 4. LEGAL & ESTABLISHMENT (FIXED: date_of_stablishment -> date_of_establishment)
	date_of_establishment = forms.DateField(
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'id': 'date'}),
		label="Date of Establishment",
		required=False # Made False based on model's null=True
	)
	ownership_type = forms.ChoiceField(
		label="", 
		choices=LenderProfile.OWNERSHIP_CHOICES, # Use model's choices
		widget=forms.Select(attrs={'class': 'form-control'}),
		required=True
	) 
	
	# 5. LENDING PARAMETERS (FIXED: min_loan/max_loan -> min_loan_amount/max_loan_amount)
	#min_loan_amount = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Minimum Loan Amount', 'min': '0.01'}), required=False)
	#max_loan_amount = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Maximum Loan Amount'}), required=False)
	#interest_rate = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Annual Interest Rate (%)', 'min': '0', 'max': '100'}), required=False)
	
	# LOAN TERMS (Use model choices for consistency)
	#loan_terms = forms.MultipleChoiceField(choices=LenderProfile.LOAN_TERM_CHOICES, 
	#	widget=forms.CheckboxSelectMultiple,
	#	required=False,
	#	label="Available Loan Terms"
	#)

	# 6. CBL COMPLIANCE (FIXED: licence_no -> cbl_license_number, regulatory_body_no -> regulatory_body_membership_number)
	cbl_license_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CBL License Number'}), required=False)
	cbl_license_expiry = forms.DateField( # New
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
		label="CBL License Expiry Date",
		required=False
	)
	cbl_tier = forms.ChoiceField(label="", choices=LenderProfile.CBL_TIER_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=False) # New
	platform_tier = forms.ChoiceField(label="", choices=LenderProfile.PLATFORM_TIER_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=False) # New
	operating_under_platform = forms.BooleanField(label="Operating under Platform License?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # New

	# 7. CAPITAL
	stated_capital = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Stated Capital (M)'}), required=False) # New
	total_assets = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Total Assets (M)'}), required=False) # New
	
	# 8. REGULATORY BODY (FIXED: regulatory_body_no -> regulatory_body_membership_number)
	cbl_license_status = forms.ChoiceField(label="", choices=LenderProfile.CBL_LICENSE_STATUS_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=False) # New
	regulatory_body_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Regulatory Body Name'}), required=False)
	regulatory_body_membership_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Membership Number'}), required=False) # Changed to match model
	association_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Industry Association Name'}), required=False)
	association_membership_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Association Membership No'}), required=False) # Changed to match model

	# 9. POLICY BOOLEANS (FIXED: kyc_policy_implementation -> has_kyc_policy etc.)
	# We use CheckboxInput for BooleanFields, not Select.
	has_kyc_policy = forms.BooleanField(label="Has KYC Policy?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
	has_aml_policy = forms.BooleanField(label="Has AML Policy?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
	has_data_protection_policy = forms.BooleanField(label="Has Data Protection Policy?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
	has_code_of_ethics = forms.BooleanField(label="Has Code of Ethics?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False)
	has_complaints_procedure = forms.BooleanField(label="Has Complaints Procedure?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # New
	has_risk_management_policy = forms.BooleanField(label="Has Risk Management Policy?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # New
	participates_in_benchmarking = forms.BooleanField(label="Participates in Benchmarking?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # Changed to match model
	submits_regulatory_reports = forms.BooleanField(label="Submits Regulatory Reports?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # Changed to match model

	# 10. LENDING POLICY
	#missed_payment_policy = forms.ChoiceField(label="", choices=LenderProfile.MISSED_PAYMENT_POLICY_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=True)
	
	# 11. AGREEMENTS (New agree_to_cbl_compliance field added)
	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_cbl_compliance = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,) # New

	class Meta:
		model = LenderProfile
		
		fields = [
			'company_name', 'trading_name', 'registration_number', 'tax_identification_number', 
			'date_of_establishment', 'ownership_type', 'business_email', 'phone_number', 
			'alternate_phone', 'website', 'physical_address', 'city', 'district', 'postal_address',
			'ceo_first_name', 'ceo_last_name', 'ceo_email', 'ceo_phone', 'cbl_tier', 
			'cbl_license_number', 'cbl_license_expiry', 'operating_under_platform',
			'stated_capital', 'total_assets', 'min_loan_amount', 'max_loan_amount', 
			'interest_rate', 'loan_terms', 'missed_payment_policy',
			'has_kyc_policy', 'has_aml_policy', 'has_data_protection_policy', 
			'has_code_of_ethics', 'has_complaints_procedure', 'has_risk_management_policy',
			'participates_in_benchmarking', 'submits_regulatory_reports',
			'regulatory_body_name', 'regulatory_body_membership_number', 
			'association_name', 'association_membership_number', 'platform_tier',
			'agrees_to_terms', 'agrees_to_credit_conditions', 'agrees_to_cbl_compliance',
			 'passport_photo', 'cbl_license_status',
		]
		
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		# Apply form-control to all standard fields
		for field_name, field in self.fields.items():
			if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
				existing_classes = field.widget.attrs.get('class', '')
				field.widget.attrs['class'] = f'{existing_classes} form-control'.strip()

	def clean(self):
		cleaned_data = super().clean()
		min_loan = cleaned_data.get("min_loan_amount") 
		max_loan = cleaned_data.get("max_loan_amount") 

		# Check if both fields have values before comparing
		if min_loan is not None and max_loan is not None:
			if min_loan > max_loan:
				# Raise a ValidationError on the fields
				self.add_error(
					'min_loan_amount', 
					"The minimum loan amount cannot be greater than the maximum loan amount."
				)

		return cleaned_data



class LenderDocumentsForm(forms.ModelForm):
	company_registration = forms.FileField(required=True)
	financial_statements = forms.FileField(required=True)
	tax_clearance = forms.FileField(required=True)
	license_certificate = forms.FileField(required=True)
	proof_of_address = forms.FileField(required=True)
	other = forms.FileField(required=True)
	
	class Meta:
		model = LenderDocs
		fields = ['company_registration', 'financial_statements', 'tax_clearance', 'license_certificate', 'proof_of_address', 'other']


class LoanApplicationStatusForm(forms.ModelForm):
	class Meta:
		model = LoanApplication
		fields = ['status', 'rejection_reasons', 'pending_reasons']
		widgets = {
			'rejection_reasons': forms.CheckboxSelectMultiple,
			'pending_reasons': forms.CheckboxSelectMultiple,
			'status': forms.Select(attrs={'id': 'statusDropdown', 'class': 'form-control small-dropdown'}),
		}


class LoanStatusForm(forms.ModelForm):
	class Meta:
		model = Loan
		fields = ['status']
		widgets = {
			'status': forms.Select(attrs={'class': 'form-control'}),
		}


"""
Fedha-Grow — lender product configuration (lender UI)
=====================================================
Lenders create and manage their loan PRODUCTS (each with rate, amount/term
bounds, and fees). Additive: products live alongside the existing LenderProfile
terms — a lender who hasn't made products yet keeps working on the old flow;
once they add products, the borrower flow uses them.
 
Screens:
  * product_list   — the lender's products, with "add product"
  * product_edit   — create/edit a product AND its fees (fees as an inline formset)
"""

# ---------------- forms ----------------
class LenderProductForm(forms.ModelForm):
	class Meta:
		model = LenderProduct
		fields = [
			"name", "product_code", "version", "effective_from",
			"annual_interest_rate", "interest_type", "interest_calculation_note",
			"repayment_frequency", "min_amount", "max_amount", "min_term", "max_term",
			"is_active", 'repayment_structure'
		]
		widgets = {
			"name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard Personal Loan"}),
			"product_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. LP-STD-03"}),
			"version": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 03"}),
			"effective_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
			"annual_interest_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
			"interest_type": forms.Select(attrs={"class": "form-select"}),
			"interest_calculation_note": forms.TextInput(attrs={"class": "form-control",
				"placeholder": "e.g. Flat interest on the original principal"}),
			"repayment_frequency": forms.Select(attrs={"class": "form-select"}),
			"min_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
			"max_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
			"min_term": forms.NumberInput(attrs={"class": "form-control"}),
			"max_term": forms.NumberInput(attrs={"class": "form-control"}),
			"is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
			'repayment_structure': forms.Select(attrs={'class': 'form-select'}),
		}
 
	def clean(self):
		cleaned = super().clean()
		structure = cleaned.get("repayment_structure")
		mn, mx = cleaned.get("min_amount"), cleaned.get("max_amount")
		if mn and mx and mn > mx:
			raise forms.ValidationError("Minimum amount can't exceed maximum amount.")
		tmn, tmx = cleaned.get("min_term"), cleaned.get("max_term")
		if tmn and tmx and tmn > tmx:
			raise forms.ValidationError("Minimum term can't exceed maximum term.")
		
		if structure == "single_month_end":
			# Term-in-months doesn't apply — a stray value would mislead.
			for f in ("min_term", "max_term"):
				if cleaned.get(f):
					self.add_error(
						f,
						"Leave term blank for a month-end product — the due date is "
						"the end of the month the loan is taken, not a number of "
						"months.")
			# A flat monthly fee % is required (reuses annual_interest_rate).
			if not cleaned.get("annual_interest_rate"):
				self.add_error(
					"annual_interest_rate",
					"Enter the flat monthly fee as a percentage (e.g. 15 for 15%).")
			# Amount bounds still apply — a borrower needs to know min/max.
			if not cleaned.get("min_amount") or not cleaned.get("max_amount"):
				self.add_error(
					"min_amount",
					"Set the minimum and maximum amount for this loan.")
	
		elif structure == "installment":
			# Instalment loans need a term in months.
			if not cleaned.get("min_term") or not cleaned.get("max_term"):
				self.add_error(
					"min_term",
					"Set the minimum and maximum term (in months) for an "
					"instalment loan.")
		return cleaned
 

 
class ProductFeeForm(forms.ModelForm):
	class Meta:
		model = ProductFee
		fields = ["fee_type", "amount", "basis", "applicable", "note"]
		widgets = {
			"fee_type": forms.Select(attrs={"class": "form-select"}),
			"amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
			"basis": forms.Select(attrs={"class": "form-select"}),
			"applicable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
			"note": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
		}
 
 
ProductFeeFormSet = inlineformset_factory(
	LenderProduct, ProductFee, form=ProductFeeForm,
	extra=3, can_delete=True)
 
