from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class RegulatorProfile(models.Model):
    DEPARTMENT_CHOICES = (
        ('NBSD', 'Non-Bank Supervision Department'),
        ('IISSD', 'Insurance, Institutions and Supervisions Division'),
        ('LEGAL', 'Legal Department'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='regulator')
    employee_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=10, choices=DEPARTMENT_CHOICES)
    job_title = models.CharField(max_length=100) # e.g., Senior Analyst, Director
    phone_number = models.CharField(max_length=20, blank=True)
    
    # Useful for generating the final License/Letter
    digital_signature = models.ImageField(upload_to='regulator/signatures/', null=True, blank=True)
    
    # Internal track of which applications this officer is currently reviewing
    is_active_reviewer = models.BooleanField(default=True)

    is_master = models.BooleanField(default=False, 
        help_text="If true, this person can invite and manage other CBL staff."
    )


    def __str__(self):
        return f"{self.user.get_full_name()} - {self.department}"
