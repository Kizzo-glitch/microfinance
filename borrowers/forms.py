from django import forms
from loans.models import Rating
from .models import BorrowerProfile, BorrowerDocs
from loans.models import LoanApplication, LoanPayment



class RatingForm(forms.ModelForm):
	class Meta:
		model = Rating
		fields = ['rating']  # Only include the rating field
		widgets = {
			'rating': forms.Select(choices=[(i, i) for i in range(1, 6)]),  # Dropdown with options from 1 to 5
		}
		labels = {
			'rating': 'Rate this lender: (1 - 5)',
		}


class BorrowerProfileForm(forms.ModelForm):
	full_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Full Name(s)',}), required=True)
	gender = forms.Select(attrs={'class': 'form-control'})
	title = forms.Select(attrs={'class': 'form-control', 'placeholder':'Title', 'style': 'height: 100%;',})
	date_of_birth = forms.DateField(
		widget=forms.DateInput(
			attrs={
				'type': 'date',  # This makes the input render as an HTML date picker
				'class': 'form-control',  # Add the Bootstrap class for styling
				'id': 'date',  # Matches the id from your HTML example
			}
		),
		label="Date Of Birth",)  # Label for the field
	
	id_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Identity Number',}), required=True)
	marital_status = forms.Select(attrs={'class': 'form-control'})
	phone_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone Number'}), required=True)
	email_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email Address'}), required=True)  
	employer_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':"Employer's Name"}), required=True)


	employment_position = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Employment Position'}), required=True)
	
	income = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Income Amount per Month',}), required=True)
	
	position_level = forms.Select(attrs={'class': 'form-control'})
	
	home_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'My Recidential Address',}), required=True)
	employer_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'My Work Address',}), required=True)
	
	income_type = forms.Select(attrs={'class': 'form-control'})

	pay_day = forms.IntegerField(
		min_value=1, max_value=31, required=True,
		help_text="Enter the day of the month you get paid (1–31)"
	)
	
	'''pay_day = forms.DateField(
		widget=forms.DateInput(
			attrs={
				'type': 'date',  # This makes the input render as an HTML date picker
				'class': 'form-control',  # Add the Bootstrap class for styling
				'id': 'date',  # Matches the id from your HTML example
			}
		),
		label="Pay Day",  # Label for the field
	)'''
	monthly_expenses = forms.Select(attrs={'class': 'form-control'})
	existing_debts = forms.Select(attrs={'class': 'form-control'})
	employment_type = forms.Select(attrs={'class': 'form-control'})
	
	#credit_score = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'My Credit Score',}), required=True)
	#credit_intend = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Reasons why I require the Loan',}), required=True)

	is_over_18 = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	information_consent = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)


	class Meta:
		model = BorrowerProfile
		fields = (
			'full_name', 
			'gender', 
			'title', 
			'date_of_birth', 
			'id_number', 
			'marital_status', 
			'phone_number', 
			'email_address', 
			'employer_name', 
			
			'employment_position',
			'income',
			'position_level',
			'home_address',
			'employer_address',
			'income_type',
			'pay_day',
			'monthly_expenses',
			'existing_debts',
			#'credit_score',
			#'credit_intend',
			'is_over_18',
			'agrees_to_terms',
			'agrees_to_credit_conditions',
			'information_consent',
			'employment_type'
			)

class OTPForm(forms.Form):
	otp_code = forms.CharField(max_length=6)



class EmploymentTypeForm(forms.ModelForm):
	employment_type = forms.Select(attrs={'class': 'form-control'})
	class Meta:
		model = BorrowerProfile
		fields = ['employment_type']


class BorrowerDocumentsForm(forms.ModelForm):
	class Meta:
		model = BorrowerDocs
		fields = ['document_type', 'file']


class EmployedDocumentsForm(forms.ModelForm):
	id_proof = forms.FileField(required=True)
	bank_statement = forms.FileField(required=True)
	payslip = forms.FileField(required=True)
	chief_letter = forms.FileField(required=False)
	
	class Meta:
		model = BorrowerDocs
		fields = ['id_proof', 'bank_statement', 'payslip', 'chief_letter']


class SelfEmployedDocumentsForm(forms.ModelForm):
	id_proof = forms.FileField(required=True)
	business_address = forms.FileField(required=True)
	bank_statement = forms.FileField(required=True)
	customer_invoice = forms.FileField(required=False)
	supplier_invoice = forms.FileField(required=True)
	chief_letter = forms.FileField(required=True)
	tax_clearance = forms.FileField(required=False)

	class Meta:
		model = BorrowerDocs
		fields = ['id_proof', 'business_address', 'bank_statement', 'customer_invoice', 'supplier_invoice', 'chief_letter', 'tax_clearance']

class RegisteredBusinessDocumentsForm(forms.ModelForm):
	id_proof = forms.FileField(required=True)
	business_address = forms.FileField(required=True)
	bank_statement = forms.FileField(required=True)
	business_statements = forms.FileField(required=True)
	business_registration = forms.FileField(required=True)
	customer_invoice = forms.FileField(required=False)
	supplier_invoice = forms.FileField(required=True)
	tax_clearance = forms.FileField(required=False)

	class Meta:
		model = BorrowerDocs
		fields = ['id_proof', 'business_address', 'bank_statement', 'business_statements', 'business_registration', 'customer_invoice', 'supplier_invoice', 'tax_clearance']


'''class BorrowerDocumentsForm(forms.ModelForm):
	class Meta:
		model = BorrowerDocs
		fields = ['id_proof', 'bank_statement', 'payslip', 'chief_letter']'''


'''class BorrowerDocumentUploadForm2(forms.ModelForm):
	class Meta:
		model = BorrowerDocuments3
		fields = ['document_type', 'file']'''


class LoanApplicationForm(forms.ModelForm):
	loan_amount = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Loan Amount Needed',}), required=True)
	loan_term = forms.Select(attrs={'class': 'form-control'})

	class Meta:
		model = LoanApplication
		fields = [
			'loan_amount', 
			'loan_term', 
			]


class LoanPaymentForm(forms.ModelForm):
	class Meta:
		model = LoanPayment
		fields = ['amount', 'payment_method']
