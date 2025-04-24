from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import LenderProfile
from loans.models import LoanApplication, Loan


class LenderInfoForm(forms.ModelForm):
	ceo_first_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'CEO First Name'}), required=True)
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

	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)


	class Meta:
		model = LenderProfile
		fields = ('ceo_first_name', 
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
			'missed_payment_policy'
			)



class LoanApplicationStatusForm(forms.ModelForm):
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
		return cleaned_data



class LoanStatusForm(forms.ModelForm):
	class Meta:
		model = Loan
		fields = ['status']
		widgets = {
			'status': forms.Select(attrs={'class': 'form-control'}),
		}
