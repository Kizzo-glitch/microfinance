from django.contrib import admin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from regulation.models import RegulatorProfile 
from .models import User 



class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")

class RegulatorProfileInline(admin.StackedInline):
    model = RegulatorProfile
    # Include the is_master field so you can check it manually in Admin
    fields = ('is_master', 'department', 'employee_id') 
    can_delete = False
    verbose_name_plural = 'Regulator Profile'

class UserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    inlines = (RegulatorProfileInline,)
    
    list_display = ('username', 'email', 'role', 'must_change_password')

    # This controls the "ADD" screen
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            # Password fields are handled by the UserCreationForm logic, 
            # but we define the layout here.
            'fields': ('username', 'email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )

    # This controls the "EDIT" screen
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Platform Status', {'fields': ('role', 'must_change_password')}),
    )

admin.site.register(User, UserAdmin)