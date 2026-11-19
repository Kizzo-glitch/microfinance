from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import IntegrityError, transaction
from django.forms import BaseModelFormSet, modelformset_factory

from .models import MobileMoneyAccount, User




class UserRegistrationForm(UserCreationForm):
	role = forms.ChoiceField(choices=User.ROLE_CHOICES, widget=forms.RadioSelect)
	first_name = forms.CharField(max_length=100)
	last_name = forms.CharField(max_length=100)
	email = forms.CharField(max_length=100)
	phone_number = forms.CharField(max_length=100)

	
	class Meta:
		model = User
		fields = ['username', 'first_name', 'last_name', 'email','phone_number', 'password1', 'password2', 'role',]



class BorrowerRegistrationForm(UserCreationForm):
	
	email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email Address'}))
	first_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
	last_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))

	class Meta:
		model = User
		fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

	def __init__(self, *args, **kwargs):
		super(BorrowerRegistrationForm, self).__init__(*args, **kwargs)

		self.fields['username'].widget.attrs['class'] = 'form-control'
		self.fields['username'].widget.attrs['placeholder'] = 'Username'
		self.fields['username'].label = ''
		self.fields['username'].help_text = '<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.</small></span>'

		self.fields['password1'].widget.attrs['class'] = 'form-control'
		self.fields['password1'].widget.attrs['placeholder'] = 'Password'
		self.fields['password1'].label = ''
		self.fields['password1'].help_text = '<ul class="form-text text-muted small"><li>Your password can\'t be too similar to your other personal information.</li><li>Your password must contain at least 8 characters.</li><li>Your password can\'t be a commonly used password.</li><li>Your password can\'t be entirely numeric.</li></ul>'

		self.fields['password2'].widget.attrs['class'] = 'form-control'
		self.fields['password2'].widget.attrs['placeholder'] = 'Confirm Password'
		self.fields['password2'].label = ''
		self.fields['password2'].help_text = '<span class="form-text text-muted"><small>Enter the same password as before, for verification.</small></span>'




class LenderRegistrationForm(UserCreationForm):
	
	email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email Address'}))
	first_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
	last_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))

	class Meta:
		model = User
		fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

	def __init__(self, *args, **kwargs):
		super(LenderRegistrationForm, self).__init__(*args, **kwargs)

		self.fields['username'].widget.attrs['class'] = 'form-control'
		self.fields['username'].widget.attrs['placeholder'] = 'Username'
		self.fields['username'].label = ''
		self.fields['username'].help_text = '<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.</small></span>'

		self.fields['password1'].widget.attrs['class'] = 'form-control'
		self.fields['password1'].widget.attrs['placeholder'] = 'Password'
		self.fields['password1'].label = ''
		self.fields['password1'].help_text = '<ul class="form-text text-muted small"><li>Your password can\'t be too similar to your other personal information.</li><li>Your password must contain at least 8 characters.</li><li>Your password can\'t be a commonly used password.</li><li>Your password can\'t be entirely numeric.</li></ul>'

		self.fields['password2'].widget.attrs['class'] = 'form-control'
		self.fields['password2'].widget.attrs['placeholder'] = 'Confirm Password'
		self.fields['password2'].label = ''
		self.fields['password2'].help_text = '<span class="form-text text-muted"><small>Enter the same password as before, for verification.</small></span>' 



"""
Fedha-Grow — payment details form + reveal logic
================================================
A form each party uses to enter their own payment details, and a helper that
decides when the OTHER party may see them (only within an approved loan).
"""

# The field list is the same for borrower and lender (both use the mixin).
#PAYMENT_DETAIL_FIELDS = [
#    "bank_name", "bank_account_name", "bank_account_number", "bank_branch_code",
#    "mobile_money_provider", "mobile_money_number", "mobile_money_name",
#    "payment_instructions",
#]

PAYMENT_DETAIL_FIELDS = [
    "bank_name", "bank_account_name", "bank_account_number", "bank_branch_code",
    "payment_instructions",
]

BANK_FIELDS = ["bank_name", "bank_account_name", "bank_account_number", "bank_branch_code"]

PAYMENT_DETAIL_WIDGETS = {
    "bank_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard Lesotho Bank"}),
    "bank_account_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account holder name"}),
    "bank_account_number": forms.TextInput(attrs={"class": "form-control"}),
    "bank_branch_code": forms.TextInput(attrs={"class": "form-control"}),
    #"mobile_money_provider": forms.Select(attrs={"class": "form-select"}),
    #"mobile_money_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+266..."}),
    #"mobile_money_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Registered name"}),
    "payment_instructions": forms.TextInput(attrs={"class": "form-control",
                             "placeholder": "e.g. Always use your loan reference"}),
}


def make_payment_details_form(model_cls):
    """Build a ModelForm for a profile's payment details."""
    class _PaymentDetailsForm(forms.ModelForm):
        class Meta:
            model = model_cls
            fields = PAYMENT_DETAIL_FIELDS
            widgets = PAYMENT_DETAIL_WIDGETS

        def clean(self):
            cleaned = super().clean()
            # A bank account is optional (mobile money is saved separately), but
            # if any bank detail is entered, the bank name and number are needed.
            bank_entered = any(cleaned.get(f) for f in BANK_FIELDS)
            if bank_entered:
                if not cleaned.get("bank_name"):
                    self.add_error("bank_name", "Add the bank name, or clear the bank details.")
                if not cleaned.get("bank_account_number"):
                    self.add_error("bank_account_number",
                                   "Add the account number, or clear the bank details.")
            return cleaned

    return _PaymentDetailsForm



class MobileMoneyAccountForm(forms.ModelForm):
    class Meta:
        model = MobileMoneyAccount
        fields = ["provider", "number", "account_name"]
        widgets = {
            "provider": forms.Select(attrs={"class": "form-select"}),
            "number": forms.TextInput(attrs={"class": "form-control", "placeholder": "+266..."}),
            "account_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Registered name"}),
        }
 
    def clean(self):
        cleaned = super().clean()
        # if the row has any data, provider + number are both required
        provider = cleaned.get("provider")
        number = cleaned.get("number")
        if (provider or number) and not (provider and number):
            raise forms.ValidationError("Both a provider and a number are needed for a mobile-money account.")
        return cleaned
 
 
class BaseMobileMoneyFormSet(BaseModelFormSet):
    """Allows one account per provider (the database enforces it too)."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        labels = dict(MobileMoneyAccount.PROVIDER_CHOICES)
        seen = set()
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if data.get("DELETE"):
                continue
            provider = data.get("provider")
            if not provider:
                continue
            if provider in seen:
                raise forms.ValidationError(
                    f"You can only add one {labels.get(provider, provider)} account. "
                    "Remove the duplicate row.")
            seen.add(provider)


# Formset: shows existing + 2 blank rows to add, allows delete.
MobileMoneyFormSet = modelformset_factory(
    MobileMoneyAccount,
    form=MobileMoneyAccountForm,
    formset=BaseMobileMoneyFormSet,
    extra=2,
    can_delete=True,
)
 
 
def get_mobile_money_formset(profile, is_lender=False, data=None):
    """
    Build the formset scoped to THIS profile's accounts.
    `profile` is a BorrowerProfile or LenderProfile.
    """
    owner_filter = {"lender": profile} if is_lender else {"borrower": profile}
    queryset = MobileMoneyAccount.objects.filter(**owner_filter)
    return MobileMoneyFormSet(data, queryset=queryset,
                              prefix="mm")   # prefix keeps it separate from other forms
 
 
def _retire_collection(account, reason):
    """A lender's instant collection is tied to this account's provider: turn it
    off (here, and in the payment gateway once saved) if the row goes away or
    the provider changes. Changing only the number keeps it: collection goes to
    the verified merchant code, not the phone number."""
    if getattr(account, "lender_id", None) is None:
        return
    from integrations.collection import retire_for_account
    retire_for_account(account, reason)


def _save_mobile_money_rows(formset, profile, is_lender):
    for form in formset:
        # skip entirely blank extra rows
        if not form.has_changed():
            continue
        if formset.can_delete and form.cleaned_data.get("DELETE"):
            if form.instance.pk:
                _retire_collection(form.instance, "The account was removed.")
                form.instance.delete()
            continue
        if form.instance.pk and "provider" in form.changed_data:
            _retire_collection(form.instance, "The account's provider changed.")
        acct = form.save(commit=False)
        # attach to the correct owner
        if is_lender:
            acct.lender = profile
            acct.borrower = None
        else:
            acct.borrower = profile
            acct.lender = None
        acct.save()


def _conflict_error(formset):
    # Rare: two rows swapped providers in one save. Validation passes (the end
    # state is unique) but the rows can't be saved one at a time.
    formset.non_form_errors().append(
        "Those changes conflict with each other (two accounts swapped providers). "
        "Please make the change in two steps.")


def save_mobile_money_formset(formset, profile, is_lender=False):
    """
    Save the formset: create/update accounts owned by this profile, honour
    deletes, and skip blank rows. All-or-nothing: if any row fails, none are
    saved. Returns True if saved, False if invalid or not saved.
    """
    if not formset.is_valid():
        return False
    try:
        with transaction.atomic():
            _save_mobile_money_rows(formset, profile, is_lender)
    except IntegrityError:
        _conflict_error(formset)
        return False
    return True


def save_payment_details(payment_form, formset, profile, is_lender=False):
    """
    Validate and save a profile's bank details and mobile-money accounts
    together, all-or-nothing. Returns True if saved. On False, the errors are
    on the form and formset, ready to re-render.
    """
    bank_ok = payment_form.is_valid()
    mm_ok = formset.is_valid()
    if not (bank_ok and mm_ok):
        return False
    try:
        with transaction.atomic():
            payment_form.save()
            _save_mobile_money_rows(formset, profile, is_lender)
    except IntegrityError:
        _conflict_error(formset)
        return False
    return True



# ---- reveal logic: when may the counterparty see these details? ----
def borrower_details_visible_to_lender(loan_or_application, lender) -> bool:
    """
    The lender may see the BORROWER's payment details (to disburse) only for a
    loan/application that is theirs AND approved.
    """
    if getattr(loan_or_application, "lender_id", None) != getattr(lender, "id", None):
        return False
    return getattr(loan_or_application, "status", None) == "approved"



def lender_details_visible_to_borrower(loan, borrower) -> bool:
    """
    The borrower may see the LENDER's payment details (to repay) only for their
    own approved loan.
    """
    if getattr(loan, "borrower_id", None) != getattr(borrower, "id", None):
        return False
    return getattr(loan, "status", None) == "approved"