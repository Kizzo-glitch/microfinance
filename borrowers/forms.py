from django import forms
from loans.models import Rating
from .models import BorrowerProfile, BorrowerDocuments
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



'''class BorrowerProfileForm(forms.ModelForm):
	full_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Full Name'}), required=True)
	gender = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Gender'}), required=True)
	title = forms.ChoiceField(choices=[('', 
			'Select'), 
				('1', 'Mr'), 
				('2', 'Ms'), 
				('3', 'Mrs'),], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Title'}), 
				required=True,)
	date_of_birth = forms.DateField(
		widget=forms.DateInput(
			attrs={
				'type': 'date',  # This makes the input render as an HTML date picker
				'class': 'form-control',  # Add the Bootstrap class for styling
				'id': 'date',  # Matches the id from your HTML example
			}
		),
		label="Date Of Birth",)  # Label for the field
	
	id_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'ID Number'}), required=True)
	marital_status = forms.ChoiceField(choices=[('', 
			'Select'), 
				('1', 'Single'), 
				('2', 'Married'), 
				('3', 'Divorced'), 
				('4', 'Widowed')], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Marital Status'}), 
				required=True,)
	phone_number = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone Number'}), required=True)
	email_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email Address'}), required=True)  
	employer_name = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':"Employer's Name"}), required=True)


	employment_position = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Employment Position'}), required=True)
	#business_email_ddress = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Business Email Address'}), required=True)
	#ownership = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Ownership'}), required=True)
	income = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Income Amount'}), required=True)
	
	position_level = forms.ChoiceField(choices=[('', 
			'Select'), 
				('1', 'entry-level'), 
				('2', 'intermediate'), 
				('3', 'mid-level'), 
				('4', 'senior-level')], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Possition Level'}), 
				required=True,)
	
	home_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Home Address'}), required=True)
	employer_address = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':"Employer's Address"}), required=True)
	
	income_type = forms.ChoiceField(choices=[('', 
			'Select'), 
				('1', 'Salary'), 
				('2', 'Wages'),
				('3', 'Other'),], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Income Type'}), 
				required=True,)
	
	pay_date = forms.DateField(
		widget=forms.DateInput(
			attrs={
				'type': 'date',  # This makes the input render as an HTML date picker
				'class': 'form-control',  # Add the Bootstrap class for styling
				'id': 'date',  # Matches the id from your HTML example
			}
		),
		label="Pay Day",  # Label for the field
	)
	monthly_expenses = forms.ChoiceField(choices=[('', 
			'Select'), 
				('1', 'Rent'), 
				('2', 'Utilities'),
				('3', 'Debt payment'),
				('4', 'Insurence'),
				('4', 'Stokvel'),], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Monthly Expenses'}), 
				required=True,)
	existing_debts = forms.ChoiceField(choices=[
		('', 
			'Select'), 
				('1', 'Loans'), 
				('2', 'Credit Cards'),
				('3', 'Credit Accounts'),
					], 
				widget = forms.Select(attrs={'class': 'form-control', 
						'placeholder':'Existing Debts'}), 
				required=True,)
	
	credit_score = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Credit Score'}), required=True)
	credit_intend = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Credit Intend'}), required=True)
	

	
	

	is_over_18 = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_terms = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	agrees_to_credit_conditions = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,)
	information_consent = forms.BooleanField(widget=forms.CheckboxInput(
		attrs={'class': 'form-check-input'}), required=True,) '''



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
		min_value=1, max_value=31, required=False,
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
	
	credit_score = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'My Credit Score',}), required=True)
	credit_intend = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Reasons why I require the Loan',}), required=True)
	

	
	

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
			'credit_score',
			'credit_intend',
			'is_over_18',
			'agrees_to_terms',
			'agrees_to_credit_conditions',
			'information_consent'
			)



class BorrowerDocumentsForm(forms.ModelForm):
	class Meta:
		model = BorrowerDocuments
		fields = ['id_proof', 'bank_statement', 'payslip', 'chief_letter']



class LoanApplicationForm(forms.ModelForm):
	loan_amount = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Loan Amount Needed',}), required=True)
	loan_term = forms.Select(attrs={'class': 'form-control'})

	#collateral = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Collateral',}), required=True)
	#payment_plan = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':'Payment Plan',}), required=True)
	#interest_rate = forms.CharField(label="", widget=forms.TextInput(attrs={'class':'form-control','placeholder':"Lender's Interest Rate",}), required=True)
	
	
	class Meta:
		model = LoanApplication
		fields = [
			'loan_amount', 
			'loan_term', 
			#'collateral', 
			#'payment_plan', 
			
			]


class LoanPaymentForm(forms.ModelForm):
	class Meta:
		model = LoanPayment
		fields = ['amount', 'payment_method']
