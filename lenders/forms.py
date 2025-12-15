from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import LenderProfile, LenderDocs
from loans.models import LoanApplication, Loan


from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
# Assuming LenderProfile, LOAN_TERM_CHOICES, etc. are imported or defined above


class LenderInfoForm(forms.ModelForm):
	
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
	min_loan_amount = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Minimum Loan Amount', 'min': '0.01'}), required=False)
	max_loan_amount = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Maximum Loan Amount'}), required=False)
	interest_rate = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Annual Interest Rate (%)', 'min': '0', 'max': '100'}), required=False)
	
	# LOAN TERMS (Use model choices for consistency)
	loan_terms = forms.MultipleChoiceField(
		choices=LenderProfile.LOAN_TERM_CHOICES, 
		widget=forms.CheckboxSelectMultiple,
		required=False,
		label="Available Loan Terms"
	)

	# 6. CBL COMPLIANCE (FIXED: licence_no -> cbl_license_number, regulatory_body_no -> regulatory_body_membership_number)
	cbl_license_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CBL License Number'}), required=False)
	cbl_license_expiry = forms.DateField( # New
		widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
		label="CBL License Expiry Date",
		required=False
	)
	cbl_tier = forms.ChoiceField(label="", choices=LenderProfile.CBL_TIER_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=False) # New
	operating_under_platform = forms.BooleanField(label="Operating under Platform License?", widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=False) # New

	# 7. CAPITAL
	stated_capital = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Stated Capital (M)'}), required=False) # New
	total_assets = forms.DecimalField(label="", widget=forms.NumberInput(attrs={'class':'form-control', 'placeholder':'Total Assets (M)'}), required=False) # New
	
	# 8. REGULATORY BODY (FIXED: regulatory_body_no -> regulatory_body_membership_number)
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
	missed_payment_policy = forms.ChoiceField(label="", choices=LenderProfile.MISSED_PAYMENT_POLICY_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}), required=True)
	
	# 11. AGREEMENTS (New agree_to_cbl_compliance field added)
	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_cbl_compliance = forms.BooleanField(widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}), required=True,) # New

	class Meta:
		model = LenderProfile
		# ⚠️ Only use fields defined in the form above
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
			'association_name', 'association_membership_number',
			'agrees_to_terms', 'agrees_to_credit_conditions', 'agrees_to_cbl_compliance'
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
		min_loan = cleaned_data.get("min_loan_amount") # Using correct model field name
		max_loan = cleaned_data.get("max_loan_amount") # Using correct model field name

		# Check if both fields have values before comparing
		if min_loan is not None and max_loan is not None:
			if min_loan > max_loan:
				# Raise a ValidationError on the fields
				self.add_error(
					'min_loan_amount', 
					"The minimum loan amount cannot be greater than the maximum loan amount."
				)

		return cleaned_data




"""
class LenderInfoForm(forms.ModelForm):
	
	ceo_first_name = forms.CharField(label="", widget=forms.TextInput(attrs={'placeholder':'CEO First Name'}), required=True)
	ceo_last_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO Last Name'}), required=True)
	company_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Company Name'}), required=True)
	registration_no = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Registration Number'}), required=True)
	office_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Office Address'}), required=True)
	min_loan = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Minimun Loan Amount'}), required=True)
	max_loan = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Maximum Loan Amount'}), required=True)
	interest_rate = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Interest Rate'}), required=True)  
	phone_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone'}), required=True)


	date_of_stablishment = forms.DateField(
		widget=forms.DateInput(
			attrs={
				'type': 'date',  # This makes the input render as an HTML date picker
				'class': 'form-control',  # Add the Bootstrap class for styling
				'id': 'date',  # Matches the id from your HTML example
			}
		),
		label="Date of Establishment",  # Label for the field
	)
	business_email_ddress = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Business Email Address'}), required=True)
	#ownership = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Ownership'}), required=True)
	ownership = forms.Select(attrs={'class': 'form-control'})
	licence_no = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'License Number'}), required=True)
	regulatory_body_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Regulatory Authority'}), required=True)
	regulatory_body_no = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Regulatory Body Number'}), required=True)
	
	kyc_policy_implementation = forms.Select(attrs={'class': 'form-control'})
	aml_policy_implementation = forms.Select(attrs={'class': 'form-control'})
	data_protection_policy_implementation = forms.Select(attrs={'class': 'form-control'})
	tax_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Tax Number'}), required=True)
	
	code_of_ethics = forms.Select(attrs={'class': 'form-control'})

	association_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Association Name'}), required=True)
	membership_no = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Membership Number'}), required=True)
	
	benchmarking = forms.Select(attrs={'class': 'form-control'})
	reporting = forms.Select(attrs={'class': 'form-control'})

	missed_payment_policy = forms.Select(attrs={'class': 'form-control'})
	loan_terms = forms.MultipleChoiceField(
		choices=[
			(1, "1 month"),
			(3, "3 months"),
			(6, "6 months"),
			(9, "9 months"),
			(12, "12 months"),
			(24, "24 months"),
			(36, "36 months"),
		],
		widget=forms.CheckboxSelectMultiple,
		required=True,
		label="Available Loan Terms"
	)

	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)


	class Meta:
		model = LenderProfile
		fields = (

				'ceo_first_name', 
				'ceo_last_name', 
				'company_name', 
				'registration_no', 
				'office_address', 
				'min_loan', 
				'max_loan', 
				'interest_rate', 
				'phone_number', 
				
				'date_of_stablishment',
				'business_email_ddress',
				'ownership',
				'licence_no',
				'regulatory_body_name',
				'regulatory_body_no',
				'kyc_policy_implementation',
				'aml_policy_implementation',
				'data_protection_policy_implementation',
				'tax_number',
				'code_of_ethics',
				'association_name',
				'membership_no',
				'benchmarking',
				'reporting',
				'missed_payment_policy',
				'loan_terms'
			)
		widgets = {
			'loan_terms': forms.CheckboxSelectMultiple(  # ✅ render as checkboxes
				attrs={'class': 'form-check-input'}
			),
		}

		
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		
		# Apply form-control to all fields
		for field_name, field in self.fields.items():
			existing_classes = field.widget.attrs.get('class', '')
			field.widget.attrs['class'] = f'{existing_classes} form-control'.strip()


	def clean(self):
		cleaned_data = super().clean()
		min_loan = cleaned_data.get("min_loan")
		max_loan = cleaned_data.get("max_loan")

		# Check if both fields have values before comparing
		if min_loan is not None and max_loan is not None:
			if min_loan > max_loan:
				# Raise a ValidationError to prevent form submission
				raise forms.ValidationError(
					"The minimum loan amount cannot be greater than the maximum loan amount."
				)

		# Always return the cleaned_data dictionary
		return cleaned_data



class VerificationStatusForm(forms.ModelForm):
	verification_status = forms.Select(attrs={'class': 'form-control'})
	class Meta:
		model = LenderProfile
		fields = ['verification_status']

"""

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


'''class LoanApplicationStatusForm(forms.ModelForm):
	class Meta:
		model = LoanApplication
		fields = ['status', 'rejection_reasons', 'pending_reasons']

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		if self.instance.status == 'rejected':
			self.fields['rejection_reasons'].widget = forms.CheckboxSelectMultiple()
		elif self.instance.status == 'pending':
			self.fields['pending_reasons'].widget = forms.CheckboxSelectMultiple()
		else:
			self.fields.pop('rejection_reasons')
			self.fields.pop('pending_reasons')'''


'''class LoanApplicationStatusForm(forms.ModelForm):
	class Meta:
		model = LoanApplication
		fields = ['status', 'status_reason']
		widgets = {
			'status': forms.Select(choices=LoanApplication.status),
		}
	def clean(self):
		cleaned_data = super().clean()
		status = cleaned_data.get("status")
		reason = cleaned_data.get("status_reason")

		if status in ['rejected', 'pending'] and not reason:
			raise forms.ValidationError("Please provide a reason for rejection or pending status.")
		return cleaned_data'''



class LoanStatusForm(forms.ModelForm):
	class Meta:
		model = Loan
		fields = ['status']
		widgets = {
			'status': forms.Select(attrs={'class': 'form-control'}),
		}




