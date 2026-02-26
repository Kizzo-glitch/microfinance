from django import forms
from .models import RegulatorProfile


class RegulatorProfileForm(forms.ModelForm):
    # Pulling fields from the User model for a seamless experience
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'readonly': 'readonly'}))

    class Meta:
        model = RegulatorProfile
        fields = ['employee_id', 'department', 'phone_number', 'job_title', 'digital_signature']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., CBL-2026-001'}),
            'department': forms.Select(attrs={'class': 'form-select'}), 
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'job_title': forms.TextInput(attrs={'class': 'form-control'}),
            
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
            self.fields['phone_number'].initial = self.instance.user.phone_number

    def save(self, commit=True):
        profile = super().save(commit=False)
        # Update the User object as well
        user = profile.user
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        if commit:
            profile.save()
        return profile
				