from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import BorrowerGroup, GroupInvite
#from micro.models import User
from borrowers.models import BorrowerProfile
from django.contrib.auth import get_user_model


User = get_user_model()


class BorrowerGroupRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    email = forms.CharField(max_length=100)
    phone_number = forms.CharField(max_length=100)


    class Meta:
        model = User
        fields = ("username", 'first_name', 'last_name', 'email','phone_number', "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.save()
        # ✅ enforce role=borrower       
        BorrowerProfile.objects.get_or_create(user=user)
        return user



class BorrowerGroupForm(forms.ModelForm):
    class Meta:
        model = BorrowerGroup
        fields = ['name', 'group_type', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Group Name'}),
            'group_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe your group'}),
        }





class GroupInviteForm(forms.ModelForm):
    class Meta:
        model = GroupInvite
        fields = ['email']
