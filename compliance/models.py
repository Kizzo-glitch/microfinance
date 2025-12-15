from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from datetime import timedelta

from lenders.models import LenderProfile

User = get_user_model()

# =================
# CBL Compliance
# =================

class CBLRegistrationManager(models.Manager):
    """Manager for CBL Registration tracking"""
    
    def active(self):
        return self.exclude(current_stage__in=['approved', 'rejected', 'withdrawn'])
    
    def awaiting_submission(self):
        return self.filter(current_stage='internal_review', submitted_to_cbl=False)
    
    def pending_cbl(self):
        return self.filter(submitted_to_cbl=True, approved=False)
    
    def approved(self):
        return self.filter(approved=True)
    
    def by_stage(self, stage):
        return self.filter(current_stage=stage)
    
    def stalled(self, days=30):
        """Registrations with no update in X days"""
        cutoff = timezone.now() - timedelta(days=days)
        return self.active().filter(updated_at__lt=cutoff)


class CBLRegistration(models.Model):
    """
    Tracks the CBL license application process.
    Separate from LenderProfile to handle the multi-stage application workflow.
    """
    
    REGISTRATION_STAGE_CHOICES = [
        ('initiated', 'Initiated'),
        ('tier_assessment', 'Tier Assessment'),
        ('company_info', 'Company Information'),
        ('directors_info', 'Directors Information'),
        ('governance_setup', 'Governance Setup'),
        ('document_collection', 'Document Collection'),
        ('document_review', 'Document Review'),
        ('application_prep', 'Application Preparation'),
        ('fee_payment', 'Fee Payment'),
        ('internal_review', 'Internal Review'),
        ('cbl_submission', 'Submitted to CBL'),
        ('cbl_review', 'Under CBL Review'),
        ('additional_info', 'Additional Info Requested'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    
    # Link to lender profile
    lender_profile = models.OneToOneField(
        LenderProfile,
        on_delete=models.CASCADE,
        related_name='cbl_registration'
    )
    
    # Application tracking
    reference_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    current_stage = models.CharField(
        max_length=30,
        choices=REGISTRATION_STAGE_CHOICES,
        default='initiated'
    )
    target_tier = models.CharField(
        max_length=20,
        choices=LenderProfile.CBL_TIER_CHOICES,
        blank=True
    )
    
    # Capital
    proposed_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    capital_source_explanation = models.TextField(blank=True)
    capital_proof_verified = models.BooleanField(default=False)
    
    # Business Plan
    business_plan_required = models.BooleanField(default=True)
    business_plan_generated = models.BooleanField(default=False)
    business_plan_approved = models.BooleanField(default=False)
    
    # Financial Statements
    requires_audited_financials = models.BooleanField(default=False)
    financials_verified = models.BooleanField(default=False)
    
    # Governance
    board_size = models.PositiveIntegerField(default=0)
    has_audit_committee = models.BooleanField(default=False)
    has_credit_committee = models.BooleanField(default=False)
    has_risk_committee = models.BooleanField(default=False)
    has_finance_manager = models.BooleanField(default=False)
    has_compliance_officer = models.BooleanField(default=False)
    
    # Manuals & Policies
    aml_manual_generated = models.BooleanField(default=False)
    aml_manual_approved = models.BooleanField(default=False)
    risk_manual_generated = models.BooleanField(default=False)
    risk_manual_approved = models.BooleanField(default=False)
    operations_manual_generated = models.BooleanField(default=False)
    complaints_procedure_generated = models.BooleanField(default=False)
    
    # CBL Application
    investigation_fee_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    investigation_fee_paid = models.BooleanField(default=False)
    investigation_fee_receipt = models.CharField(max_length=100, blank=True)
    
    # CBL Submission
    submitted_to_cbl = models.BooleanField(default=False)
    cbl_submission_date = models.DateTimeField(null=True, blank=True)
    cbl_reference_number = models.CharField(max_length=100, blank=True)
    cbl_assigned_officer = models.CharField(max_length=200, blank=True)
    cbl_feedback = models.TextField(blank=True)
    
    # Outcome
    approved = models.BooleanField(default=False)
    approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    license_issue_date = models.DateField(null=True, blank=True)
    license_expiry_date = models.DateField(null=True, blank=True)
    
    # Interim Operations
    interim_operations_approved = models.BooleanField(
        default=False,
        help_text="Approved to operate under platform while CBL pending"
    )
    interim_max_exposure = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'CBL Registration'
        verbose_name_plural = 'CBL Registrations'
    
    def __str__(self):
        return f"{self.reference_number} - {self.lender_profile.company_name}"
    
    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self.generate_reference_number()
        
        # Auto-set requirements based on tier
        if self.target_tier and not self.pk:
            self.set_tier_requirements()
        
        super().save(*args, **kwargs)
    
    def generate_reference_number(self):
        """Generate unique reference number"""
        year = timezone.now().year
        count = CBLRegistration.objects.filter(
            created_at__year=year
        ).count() + 1
        return f"CBL-{year}-{count:04d}"
    
    def set_tier_requirements(self):
        """Set requirements based on target tier"""
        if self.target_tier == 'tier1':
            self.business_plan_required = True
            self.requires_audited_financials = True
        elif self.target_tier == 'tier2':
            self.business_plan_required = True
            self.requires_audited_financials = True
        elif self.target_tier == 'tier3':
            self.business_plan_required = False
            self.requires_audited_financials = False
    

    def active(self):
        return self.exclude(current_stage__in=['approved', 'rejected', 'withdrawn'])
    
    def awaiting_submission(self):
        return self.filter(current_stage='internal_review', submitted_to_cbl=False)
    
    def pending_cbl(self):
        return self.filter(submitted_to_cbl=True, approved=False)
    
    def approved(self):
        return self.filter(approved=True)
    
    def by_stage(self, stage):
        return self.filter(current_stage=stage)
    
    def stalled(self, days=30):
        """Registrations with no update in X days"""
        cutoff = timezone.now() - timedelta(days=days)
        return self.active().filter(updated_at__lt=cutoff)
    
    def get_completion_percentage(self):
        """Calculate overall completion percentage"""
        requirements = self.get_all_requirements()
        if not requirements:
            return 0
        completed = sum(1 for req in requirements if req['completed'])
        return int((completed / len(requirements)) * 100)
    
    def get_all_requirements(self):
        """Get all requirements with completion status"""
        requirements = []
        
        # Company Information
        lp = self.lender_profile
        requirements.append({
            'category': 'company',
            'name': 'Company Registration',
            'completed': bool(lp.registration_number),
            'required': True
        })
        requirements.append({
            'category': 'company',
            'name': 'Tax Clearance',
            'completed': bool(lp.tax_identification_number),
            'required': True
        })
        requirements.append({
            'category': 'capital',
            'name': 'Proof of Capital',
            'completed': self.capital_proof_verified,
            'required': True
        })
        
        # Business Plan
        if self.business_plan_required:
            requirements.append({
                'category': 'documentation',
                'name': 'Business Plan',
                'completed': self.business_plan_approved,
                'required': True
            })
        
        # Financial Statements
        if self.requires_audited_financials:
            requirements.append({
                'category': 'documentation',
                'name': 'Audited Financial Statements',
                'completed': self.financials_verified,
                'required': True
            })
        
        # Directors
        min_board = lp.minimum_board_size
        if min_board > 0:
            actual_directors = self.key_personnel.filter(role='director').count()
            requirements.append({
                'category': 'governance',
                'name': f'Board of Directors ({min_board}+ members)',
                'completed': actual_directors >= min_board,
                'required': True
            })
        
        # Governance Committees (Tier 1)
        if self.target_tier == 'tier1':
            requirements.append({
                'category': 'governance',
                'name': 'Internal Audit Committee',
                'completed': self.has_audit_committee,
                'required': True
            })
            requirements.append({
                'category': 'governance',
                'name': 'Board Credit Committee',
                'completed': self.has_credit_committee,
                'required': True
            })
        
        # Key Personnel (Tier 1 & 2)
        if self.target_tier in ['tier1', 'tier2']:
            requirements.append({
                'category': 'personnel',
                'name': 'Finance Manager',
                'completed': self.has_finance_manager,
                'required': True
            })
            requirements.append({
                'category': 'personnel',
                'name': 'Compliance Officer',
                'completed': self.has_compliance_officer,
                'required': True
            })
        
        # Compliance Documents
        requirements.append({
            'category': 'compliance',
            'name': 'AML/CFT Manual',
            'completed': self.aml_manual_approved,
            'required': True
        })
        
        if self.target_tier in ['tier1', 'tier2']:
            requirements.append({
                'category': 'compliance',
                'name': 'Risk Management Manual',
                'completed': self.risk_manual_approved,
                'required': True
            })
        
        requirements.append({
            'category': 'compliance',
            'name': 'Consumer Complaints Procedure',
            'completed': self.complaints_procedure_generated,
            'required': True
        })
        
        # Application
        requirements.append({
            'category': 'application',
            'name': 'Investigation Fee Payment',
            'completed': self.investigation_fee_paid,
            'required': True
        })
        
        return requirements
    
    def advance_stage(self):
        """Move to next stage if current stage is complete"""
        stage_order = [s[0] for s in self.REGISTRATION_STAGE_CHOICES]
        current_index = stage_order.index(self.current_stage)
        
        if current_index < len(stage_order) - 1:
            self.current_stage = stage_order[current_index + 1]
            self.save()
            return True
        return False


class KeyPersonnel(models.Model):
    """
    Directors, Officers, and Key Personnel for CBL compliance.
    Consolidated model to avoid duplication.
    """
    
    ROLE_CHOICES = [
        ('director', 'Director'),
        ('chairman', 'Chairman'),
        ('ceo', 'Chief Executive Officer'),
        ('cfo', 'Chief Financial Officer'),
        ('finance_manager', 'Finance Manager'),
        ('compliance_officer', 'Compliance Officer'),
        ('risk_officer', 'Risk Officer'),
        ('internal_auditor', 'Internal Auditor'),
        ('company_secretary', 'Company Secretary'),
        ('shareholder', 'Major Shareholder'),
    ]
    
    COMMITTEE_CHOICES = [
        ('audit', 'Audit Committee'),
        ('credit', 'Credit Committee'),
        ('risk', 'Risk Committee'),
        ('remuneration', 'Remuneration Committee'),
    ]
    
    # Relationship
    registration = models.ForeignKey(
        CBLRegistration,
        on_delete=models.CASCADE,
        related_name='key_personnel'
    )
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    national_id = models.CharField(max_length=50)
    passport_number = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField()
    nationality = models.CharField(max_length=100, default='Mosotho')
    gender = models.CharField(
        max_length=10,
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        blank=True
    )
    
    # Contact Information
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    physical_address = models.TextField()
    postal_address = models.CharField(max_length=200, blank=True)
    
    # Role Information
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    is_executive = models.BooleanField(
        default=False,
        help_text="Is this an executive (employed) position?"
    )
    appointment_date = models.DateField(null=True, blank=True)
    committee_memberships = models.JSONField(
        default=list,
        blank=True,
        help_text="List of committee memberships"
    )
    
    # Shareholding (for directors/shareholders)
    shareholding_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Professional Information
    qualifications = models.TextField(blank=True)
    professional_memberships = models.TextField(blank=True)
    years_of_experience = models.PositiveIntegerField(default=0)
    current_employer = models.CharField(max_length=200, blank=True)
    current_position = models.CharField(max_length=200, blank=True)
    
    # Fit & Proper Declaration
    other_mfi_directorships = models.TextField(
        blank=True,
        help_text="List other MFI directorships (should be none for Tier 1/2)"
    )
    has_criminal_record = models.BooleanField(default=False)
    has_bankruptcy_history = models.BooleanField(default=False)
    has_regulatory_sanctions = models.BooleanField(default=False)
    declaration_notes = models.TextField(blank=True)
    
    # LIA Membership (for finance roles)
    is_lia_member = models.BooleanField(
        default=False,
        help_text="Lesotho Institute of Accountants member"
    )
    lia_membership_number = models.CharField(max_length=50, blank=True)
    
    # Verification Status
    documents_complete = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_personnel'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['role', 'last_name']
        verbose_name = 'Key Personnel'
        verbose_name_plural = 'Key Personnel'
        unique_together = ['registration', 'national_id']
    
    def __str__(self):
        return f"{self.full_name} - {self.get_role_display()}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_director(self):
        return self.role in ['director', 'chairman']
    
    @property
    def required_documents(self):
        """Return list of required document types for this role"""
        base_docs = [
            'id_copy',
            'proof_of_address',
            'police_clearance',
            'tax_clearance',
            'cv_resume',
        ]
        
        if self.is_director:
            base_docs.extend([
                'fit_proper_questionnaire',
                'character_reference_1',
                'character_reference_2',
                'bank_reference',
                'schedule_iii_form',
                'asset_liability_statement',
            ])
        
        if self.role in ['finance_manager', 'cfo']:
            base_docs.extend([
                'lia_membership_certificate',
                'lia_practicing_certificate',
            ])
        
        return base_docs
    
    def check_documents_complete(self):
        """Check if all required documents are uploaded"""
        required = set(self.required_documents)
        uploaded = set(
            self.documents.values_list('document_type', flat=True)
        )
        self.documents_complete = required.issubset(uploaded)
        self.save(update_fields=['documents_complete'])
        return self.documents_complete
    
    def clean(self):
        """Validation"""
        errors = {}
        
        # Check shareholding limit (CBL: max 25% for regulated MFIs)
        if self.shareholding_percentage and self.shareholding_percentage > 25:
            tier = self.registration.target_tier
            if tier in ['tier1', 'tier2']:
                errors['shareholding_percentage'] = 'Maximum shareholding is 25% for Tier 1/2 MFIs'
        
        # Check other directorships
        if self.is_director and self.other_mfi_directorships:
            tier = self.registration.target_tier
            if tier in ['tier1', 'tier2']:
                errors['other_mfi_directorships'] = 'Directors of Tier 1/2 MFIs cannot hold other MFI directorships'
        
        # LIA membership for finance roles
        if self.role in ['finance_manager', 'cfo'] and not self.is_lia_member:
            # Warning, not error - can be outsourced
            pass
        
        if errors:
            raise ValidationError(errors)


class ComplianceDocument(models.Model):
    """
    Unified document storage for all CBL compliance documents.
    Can be attached to LenderProfile, CBLRegistration, or KeyPersonnel.
    """
    
    DOCUMENT_CATEGORY_CHOICES = [
        ('company', 'Company Documents'),
        ('personnel', 'Personnel Documents'),
        ('governance', 'Governance Documents'),
        ('compliance', 'Compliance Policies'),
        ('financial', 'Financial Documents'),
        ('application', 'CBL Application Documents'),
        ('ongoing', 'Ongoing Compliance'),
    ]
    
    DOCUMENT_TYPE_CHOICES = [
        # Company Documents
        ('company_registration', 'Company Registration Certificate'),
        ('memorandum_articles', 'Memorandum & Articles of Association'),
        ('tax_clearance_company', 'Company Tax Clearance'),
        ('business_license', 'Business License'),
        ('vat_registration', 'VAT Registration Certificate'),
        
        # Capital & Financial
        ('bank_statement', 'Bank Statement (Capital Proof)'),
        ('audited_financials', 'Audited Financial Statements'),
        ('certified_accounts', 'Certified Accountant Statements'),
        ('financial_projections', 'Financial Projections'),
        
        # Business Planning
        ('business_plan', 'Business Plan'),
        ('strategic_plan', 'Strategic Plan'),
        ('organizational_chart', 'Organizational Chart'),
        
        # Governance
        ('board_resolution', 'Board Resolution'),
        ('board_minutes', 'Board Meeting Minutes'),
        ('shareholding_structure', 'Shareholding Structure'),
        ('committee_charter', 'Committee Charter'),
        
        # Compliance Manuals
        ('aml_manual', 'AML/CFT Policy Manual'),
        ('risk_manual', 'Risk Management Manual'),
        ('operations_manual', 'Operations Manual'),
        ('credit_policy', 'Credit Policy'),
        ('complaints_procedure', 'Consumer Complaints Procedure'),
        ('data_protection_policy', 'Data Protection Policy'),
        ('code_of_ethics', 'Code of Ethics'),
        
        # Personnel Documents
        ('id_copy', 'National ID / Passport Copy'),
        ('proof_of_address', 'Proof of Address'),
        ('police_clearance', 'Police Clearance Certificate'),
        ('tax_clearance', 'Personal Tax Clearance'),
        ('cv_resume', 'CV / Resume'),
        ('fit_proper_questionnaire', 'Fit & Proper Questionnaire'),
        ('character_reference_1', 'Character Reference Letter 1'),
        ('character_reference_2', 'Character Reference Letter 2'),
        ('bank_reference', 'Bank/Financial Reference'),
        ('schedule_iii_form', 'Schedule III Form'),
        ('asset_liability_statement', 'Statement of Assets & Liabilities'),
        ('lia_membership_certificate', 'LIA Membership Certificate'),
        ('lia_practicing_certificate', 'LIA Practicing Certificate'),
        ('service_level_agreement', 'Service Level Agreement'),
        
        # CBL Application
        ('application_form_schedule1', 'Application Form (Schedule I)'),
        ('application_form_schedule2', 'Application Form (Schedule II)'),
        ('investigation_fee_receipt', 'Investigation Fee Receipt'),
        ('cbl_correspondence', 'CBL Correspondence'),
        ('license_certificate', 'License Certificate'),
        
        # Ongoing Compliance
        ('quarterly_report', 'Quarterly Prudential Report'),
        ('annual_report', 'Annual Report'),
        ('external_audit_report', 'External Audit Report'),
        ('compliance_certificate', 'Compliance Certificate'),
        
        # Other
        ('other', 'Other Document'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Upload'),
        ('uploaded', 'Uploaded'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    # Polymorphic relationships (use only one)
    lender_profile = models.ForeignKey(
        LenderProfile,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='compliance_documents'
    )
    cbl_registration = models.ForeignKey(
        CBLRegistration,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    key_personnel = models.ForeignKey(
        KeyPersonnel,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    
    # Document Information
    category = models.CharField(max_length=30, choices=DOCUMENT_CATEGORY_CHOICES)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # File
    file = models.FileField(upload_to='compliance_documents/%Y/%m/')
    file_size = models.PositiveIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    
    # Version Control
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    replaces = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replaced_by'
    )
    
    # Validity
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    
    # Status & Review
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='uploaded'
    )
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_documents'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_documents'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Compliance Document'
        verbose_name_plural = 'Compliance Documents'
    
    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()})"
    
    @property
    def is_expired(self):
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.now().date()
    
    @property
    def expires_soon(self):
        """Check if expiring within 30 days"""
        if not self.expiry_date:
            return False
        days_until = (self.expiry_date - timezone.now().date()).days
        return 0 < days_until <= 30
    
    def save(self, *args, **kwargs):
        # Auto-set file metadata
        if self.file:
            self.file_size = self.file.size
            self.original_filename = self.file.name
        
        # Mark previous versions as not current
        if self.is_current and self.pk is None:
            self.__class__.objects.filter(
                document_type=self.document_type,
                lender_profile=self.lender_profile,
                cbl_registration=self.cbl_registration,
                key_personnel=self.key_personnel,
                is_current=True
            ).update(is_current=False)
        
        super().save(*args, **kwargs)


class ComplianceChecklist(models.Model):
    """
    Track individual compliance requirements for a registration.
    Auto-generated based on tier.
    """
    
    PRIORITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    
    registration = models.ForeignKey(
        CBLRegistration,
        on_delete=models.CASCADE,
        related_name='checklist_items'
    )
    
    category = models.CharField(max_length=50)
    requirement = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    
    is_mandatory = models.BooleanField(default=True)
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='high'
    )
    
    # Tier applicability
    applies_to_tier1 = models.BooleanField(default=True)
    applies_to_tier2 = models.BooleanField(default=True)
    applies_to_tier3 = models.BooleanField(default=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    evidence_document = models.ForeignKey(
        ComplianceDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='satisfies_requirements'
    )
    notes = models.TextField(blank=True)
    
    # Due date
    due_date = models.DateField(null=True, blank=True)
    
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['category', 'order']
        verbose_name = 'Compliance Checklist Item'
        verbose_name_plural = 'Compliance Checklist Items'
    
    def __str__(self):
        status = "✓" if self.is_completed else "○"
        return f"{status} {self.requirement}"
    
    @property
    def is_overdue(self):
        if not self.due_date or self.is_completed:
            return False
        return self.due_date < timezone.now().date()
    
    def mark_complete(self, user, document=None, notes=''):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.completed_by = user
        self.evidence_document = document
        self.notes = notes
        self.save()


class OngoingComplianceReport(models.Model):
    """
    Track ongoing compliance reporting requirements (post-licensing).
    """
    
    REPORT_TYPE_CHOICES = [
        ('quarterly_prudential', 'Quarterly Prudential Report'),
        ('annual_return', 'Annual Return'),
        ('aml_sar', 'Suspicious Activity Report'),
        ('credit_bureau', 'Credit Bureau Submission'),
        ('external_audit', 'External Audit Report'),
        ('license_renewal', 'License Renewal Application'),
        ('material_change', 'Material Change Notification'),
        ('complaints_summary', 'Complaints Summary Report'),
    ]
    
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
        ('as_needed', 'As Needed'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Submitted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected - Resubmission Required'),
    ]
    
    lender_profile = models.ForeignKey(
        LenderProfile,
        on_delete=models.CASCADE,
        related_name='compliance_reports'
    )
    
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    
    # Period
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    
    # Submission
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='submitted_reports'
    )
    
    # Document
    report_document = models.ForeignKey(
        ComplianceDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='report_submissions'
    )
    
    # Feedback
    cbl_feedback = models.TextField(blank=True)
    cbl_received_date = models.DateField(null=True, blank=True)
    
    # Auto-generated
    is_auto_generated = models.BooleanField(default=False)
    generated_data = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-due_date']
        verbose_name = 'Ongoing Compliance Report'
        verbose_name_plural = 'Ongoing Compliance Reports'
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.period_end}"
    
    @property
    def is_overdue(self):
        if self.status in ['submitted', 'accepted']:
            return False
        return self.due_date < timezone.now().date()
    
    @property
    def days_until_due(self):
        return (self.due_date - timezone.now().date()).days





"""
class LenderComplianceRecord(models.Model):

    TIER_CHOICES = [
        ('individual', 'Individual Lender (Under Platform)'),
        ('tier3', 'Tier 3: Small Credit-Only MFI'),
        ('tier2', 'Tier 2: Large Credit-Only MFI'),
        ('tier1', 'Tier 1: Deposit-Taking MFI'),
    ]

    STAGE_CHOICES = [
        ('tier_selection', 'Tier Selection'),
        ('company_info', 'Company Information'),
        ('directors', 'Directors Upload'),
        ('governance', 'Governance Setup'),
        ('manuals', 'Compliance Manuals'),
        ('forms', 'Application Forms'),
        ('submission', 'CBL Submission'),
        ('pending', 'Pending CBL Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    lender = models.OneToOneField(
        LenderProfile,
        on_delete=models.CASCADE,
        related_name='compliance_record'
    )

    tier = models.CharField(max_length=20, choices=TIER_CHOICES)
    stage = models.CharField(max_length=30, choices=STAGE_CHOICES, default='tier_selection')

    company_name = models.CharField(max_length=255, blank=True)
    capital_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    capital_source = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company_name or self.lender.user.username} - {self.get_tier_display()}"


class CompanyInformation(models.Model):
    record = models.OneToOneField(
        LenderComplianceRecord,
        on_delete=models.CASCADE,
        related_name='company_info'
    )

    registration_cert = models.FileField(upload_to='cbl/company/', null=True, blank=True)
    memorandum_articles = models.FileField(upload_to='cbl/company/', null=True, blank=True)
    tax_clearance = models.FileField(upload_to='cbl/company/', null=True, blank=True)
    proof_of_capital = models.FileField(upload_to='cbl/company/', null=True, blank=True)

    def is_complete(self):
        return all([
            self.registration_cert,
            self.tax_clearance,
            self.proof_of_capital,
        ])


class Director(models.Model):
    record = models.ForeignKey(
        LenderComplianceRecord,
        on_delete=models.CASCADE,
        related_name='directors'
    )

    full_name = models.CharField(max_length=150)
    national_id = models.CharField(max_length=50)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    dob = models.DateField()

    # Documents
    fit_proper_form = models.FileField(upload_to='cbl/directors/fit_proper/', null=True, blank=True)
    police_clearance = models.FileField(upload_to='cbl/directors/police/', null=True, blank=True)
    tax_clearance = models.FileField(upload_to='cbl/directors/tax/', null=True, blank=True)
    id_copy = models.FileField(upload_to='cbl/directors/id/', null=True, blank=True)

    def is_complete(self):
        return all([
            self.fit_proper_form,
            self.police_clearance,
            self.tax_clearance,
            self.id_copy,
        ])

class GovernanceSetup(models.Model):
    record = models.OneToOneField(
        LenderComplianceRecord,
        on_delete=models.CASCADE,
        related_name='governance'
    )

    board_size = models.IntegerField(default=0)
    has_internal_audit_committee = models.BooleanField(default=False)
    has_credit_committee = models.BooleanField(default=False)
    has_finance_manager = models.BooleanField(default=False)

    def is_complete(self):
        return (
            self.board_size >= 1 and  # Tier-specific rules handled in service
            self.has_finance_manager
        )

class ComplianceManuals(models.Model):
    record = models.OneToOneField(
        LenderComplianceRecord,
        on_delete=models.CASCADE,
        related_name='manuals'
    )

    aml_manual = models.FileField(upload_to='cbl/manuals/aml/', null=True, blank=True)
    risk_manual = models.FileField(upload_to='cbl/manuals/risk/', null=True, blank=True)
    consumer_complaints_procedure = models.FileField(upload_to='cbl/manuals/consumer/', null=True, blank=True)

    def is_complete(self):
        return all([
            self.aml_manual,
            self.consumer_complaints_procedure
        ])

class CBLSubmission(models.Model):
    record = models.OneToOneField(
        LenderComplianceRecord,
        on_delete=models.CASCADE,
        related_name='submission'
    )

    schedule1_form = models.FileField(upload_to='cbl/forms/', null=True, blank=True)
    schedule2_form = models.FileField(upload_to='cbl/forms/', null=True, blank=True)
    investigation_fee_receipt = models.FileField(upload_to='cbl/payments/', null=True, blank=True)
    submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)

    def is_complete(self):
        return all([
            self.schedule1_form,
            self.schedule2_form,
            self.investigation_fee_receipt,
        ])





class LenderCBLRegistration(models.Model):

    TIER_CHOICES = [
        ('individual', 'Individual Lender (Under Platform)'),
        ('tier3', 'Tier 3 – Small Credit-Only Institution'),
        ('tier2', 'Tier 2 – Large Credit-Only Institution'),
        ('tier1', 'Tier 1 – Deposit-Taking MFI'),
    ]

    STAGES = [
        ('tier_selection', 'Tier Selection'),
        ('company_info', 'Company Information'),
        ('directors', 'Directors'),
        ('governance', 'Governance Setup'),
        ('documents', 'Document Upload'),
        ('application_pack', 'Application Pack Generation'),
        ('fee_payment', 'Investigation Fee Payment'),
        ('submission', 'CBL Submission'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Main link to lender
    lender = models.OneToOneField(LenderProfile, on_delete=models.CASCADE, related_name="cbl_registration")

    # Basic registration info
    company_name = models.CharField(max_length=255)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES)
    capital_amount = models.DecimalField(max_digits=12, decimal_places=2)
    capital_source = models.TextField()

    # Registration status
    current_stage = models.CharField(max_length=50, choices=STAGES, default='tier_selection')

    submitted_to_cbl = models.BooleanField(default=False)
    cbl_reference_number = models.CharField(max_length=200, blank=True)
    approval_date = models.DateField(null=True, blank=True)
    license_number = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---- Tier logic ----------------------------------------------------
    def required_director_count(self):
        if self.tier in ['tier1', 'tier2']:
            return 5
        return 1

    def is_business_plan_required(self):
        return self.tier in ['tier1', 'tier2']

    def is_finance_function_required(self):
        return self.tier in ['tier1', 'tier2']

    def is_full_compliance_required(self):
        return self.tier == 'tier1'

    def __str__(self):
        return f"{self.company_name} ({self.get_tier_display()})"


class Director(models.Model):
    registration = models.ForeignKey(
        LenderCBLRegistration,
        on_delete=models.CASCADE,
        related_name="directors"
    )

    full_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=50)
    email = models.EmailField()
    phone = models.CharField(max_length=25)
    address = models.TextField()

    # Documents
    fit_and_proper = models.FileField(upload_to="cbl/directors/fit/", null=True, blank=True)
    id_copy = models.FileField(upload_to="cbl/directors/id/", null=True, blank=True)
    police_clearance = models.FileField(upload_to="cbl/directors/police/", null=True, blank=True)
    tax_clearance = models.FileField(upload_to="cbl/directors/tax/", null=True, blank=True)
    bank_reference = models.FileField(upload_to="cbl/directors/bank/", null=True, blank=True)

    verified = models.BooleanField(default=False)


class FinanceFunction(models.Model):
    registration = models.OneToOneField(
        LenderCBLRegistration,
        on_delete=models.CASCADE,
        related_name="finance_function"
    )

    full_name = models.CharField(max_length=200)
    is_lia_member = models.BooleanField(default=False)
    lia_certificate = models.FileField(upload_to="cbl/finance/lia/", null=True, blank=True)
    police_clearance = models.FileField(upload_to="cbl/finance/police/", null=True, blank=True)


class ComplianceFunction(models.Model):
    registration = models.OneToOneField(
        LenderCBLRegistration,
        on_delete=models.CASCADE,
        related_name="compliance_function"
    )

    full_name = models.CharField(max_length=200)
    qualifications = models.TextField()
    police_clearance = models.FileField(upload_to="cbl/compliance/police/", null=True, blank=True)


class RegistrationDocument(models.Model):
    registration = models.ForeignKey(
        LenderCBLRegistration,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    type = models.CharField(max_length=100)
    file = models.FileField(upload_to="cbl/documents/")
    verified = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class ComplianceRequirement(models.Model):
    registration = models.ForeignKey(
        LenderCBLRegistration,
        on_delete=models.CASCADE,
        related_name="requirements"
    )
    category = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    description = models.TextField()
    mandatory = models.BooleanField(default=True)

    completed = models.BooleanField(default=False)
    evidence = models.FileField(upload_to="cbl/requirements/", null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class RequirementEvaluatorService:

    def __init__(self, registration):
        self.registration = registration

    def directors_ok(self):
        return self.registration.directors.count() >= self.registration.required_director_count()

    def finance_ok(self):
        if not self.registration.is_finance_function_required():
            return True
        return hasattr(self.registration, "finance_function")

    def compliance_ok(self):
        if not self.registration.is_full_compliance_required():
            return True
        return hasattr(self.registration, "compliance_function")

    def documents_ok(self):
        completed = self.registration.requirements.filter(completed=True).count()
        total = self.registration.requirements.count()
        return completed == total

    def calculate_completion_percentage(self):
        total = self.registration.requirements.count()
        if total == 0:
            return 0
        completed = self.registration.requirements.filter(completed=True).count()
        return int((completed / total) * 100)



class CBLLenderRegistration(models.Model):
    #CBL-compliant lender registration
    
    CBL_TIERS = [
        ('tier1', 'Tier 1 - Deposit-Taking MFI'),
        ('tier2', 'Tier 2 - Credit-Only (Large, Assets ≥ M10M)'),
        ('tier3', 'Tier 3 - Credit-Only (Small, Assets < M10M)'),
        ('individual', 'Individual Lender (Under Platform)'),
    ]
    
    REGISTRATION_STAGES = [
        ('tier_selection', 'Tier Selection'),
        ('company_info', 'Company Information'),
        ('directors_info', 'Directors Information'),
        ('governance_setup', 'Governance Setup'),
        ('document_upload', 'Document Upload'),
        ('application_review', 'Application Review'),
        ('fee_payment', 'Fee Payment'),
        ('cbl_submission', 'CBL Submission'),
        ('pending_approval', 'Pending CBL Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    # Basic Information
    applicant = models.OneToOneField(LenderProfile, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=200)
    tier = models.CharField(max_length=20, choices=CBL_TIERS)
    current_stage = models.CharField(max_length=50, choices=REGISTRATION_STAGES, default='tier_selection')
    
    # Capital Information
    proposed_capital = models.DecimalField(max_digits=12, decimal_places=2, help_text="Minimum capital to commit")
    capital_source = models.TextField(help_text="Explain source of capital")
    has_capital_proof = models.BooleanField(default=False)
    
    # Company Documents
    company_registration_cert = models.FileField(upload_to='cbl_applications/company/', null=True, blank=True)
    memorandum_articles = models.FileField(upload_to='cbl_applications/company/', null=True, blank=True)
    tax_clearance_company = models.FileField(upload_to='cbl_applications/company/', null=True, blank=True)
    
    # Business Plan
    business_plan_required = models.BooleanField(default=True)  # False for Tier 3
    business_plan_generated = models.BooleanField(default=False)
    business_plan_file = models.FileField(upload_to='cbl_applications/business_plans/', null=True, blank=True)
    
    # Financial Statements
    audited_financials_required = models.BooleanField(default=True)  # False for Tier 3
    audited_financials = models.FileField(upload_to='cbl_applications/financials/', null=True, blank=True)
    certified_accountant_statements = models.FileField(upload_to='cbl_applications/financials/', null=True, blank=True)
    
    # Governance
    board_size = models.IntegerField(default=0)
    has_internal_audit_committee = models.BooleanField(default=False)  # Tier 1 only
    has_board_credit_committee = models.BooleanField(default=False)  # Tier 1 only
    has_finance_manager = models.BooleanField(default=False)  # Tier 1, 2
    
    # AML/CFT Compliance
    aml_manual_generated = models.BooleanField(default=False)
    aml_manual_file = models.FileField(upload_to='cbl_applications/aml/', null=True, blank=True)
    
    # Risk Management
    risk_manual_required = models.BooleanField(default=True)  # False for Tier 3
    risk_manual_generated = models.BooleanField(default=False)
    risk_manual_file = models.FileField(upload_to='cbl_applications/risk/', null=True, blank=True)
    
    # Consumer Protection
    complaints_procedure_file = models.FileField(upload_to='cbl_applications/consumer/', null=True, blank=True)
    
    # CBL Application
    application_form_schedule1 = models.FileField(upload_to='cbl_applications/forms/', null=True, blank=True)
    application_form_schedule2 = models.FileField(upload_to='cbl_applications/forms/', null=True, blank=True)
    investigation_fee_paid = models.BooleanField(default=False)
    investigation_fee_receipt = models.FileField(upload_to='cbl_applications/payments/', null=True, blank=True)
    
    # Submission
    submitted_to_cbl = models.BooleanField(default=False)
    cbl_submission_date = models.DateTimeField(null=True, blank=True)
    cbl_reference_number = models.CharField(max_length=100, blank=True)
    cbl_feedback = models.TextField(blank=True)
    
    # Approval
    approved = models.BooleanField(default=False)
    approval_date = models.DateTimeField(null=True, blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def get_required_directors_count(self):
        #Return minimum directors based on tier
        if self.tier == 'tier1' or self.tier == 'tier2':
            return 5
        return 1  # Tier 3 or individual
    
    def get_completion_percentage(self):
        #Calculate application completion
        requirements = self.get_all_requirements()
        completed = sum(1 for req in requirements if req['completed'])
        return int((completed / len(requirements)) * 100) if requirements else 0
    
    def get_all_requirements(self):
        #Get all requirements for this tier
        reqs = []
        
        # Company Information
        reqs.append({'name': 'Company Registration', 'completed': bool(self.company_registration_cert), 'category': 'company'})
        reqs.append({'name': 'Tax Clearance', 'completed': bool(self.tax_clearance_company), 'category': 'company'})
        reqs.append({'name': 'Proof of Capital', 'completed': self.has_capital_proof, 'category': 'company'})
        
        if self.business_plan_required:
            reqs.append({'name': 'Business Plan', 'completed': bool(self.business_plan_file), 'category': 'company'})
        
        if self.audited_financials_required:
            reqs.append({'name': 'Audited Financials', 'completed': bool(self.audited_financials), 'category': 'company'})
        else:
            reqs.append({'name': 'Certified Accountant Statements', 'completed': bool(self.certified_accountant_statements), 'category': 'company'})
        
        # Directors
        required_directors = self.get_required_directors_count()
        actual_directors = self.directors.count()
        reqs.append({'name': f'{required_directors}+ Directors', 'completed': actual_directors >= required_directors, 'category': 'directors'})
        
        # Governance
        if self.tier == 'tier1':
            reqs.append({'name': 'Internal Audit Committee', 'completed': self.has_internal_audit_committee, 'category': 'governance'})
            reqs.append({'name': 'Board Credit Committee', 'completed': self.has_board_credit_committee, 'category': 'governance'})
        
        if self.tier in ['tier1', 'tier2']:
            reqs.append({'name': 'Finance Manager', 'completed': self.has_finance_manager, 'category': 'governance'})
        
        # Compliance
        reqs.append({'name': 'AML/CFT Manual', 'completed': bool(self.aml_manual_file), 'category': 'compliance'})
        
        if self.risk_manual_required:
            reqs.append({'name': 'Risk Management Manual', 'completed': bool(self.risk_manual_file), 'category': 'compliance'})
        
        reqs.append({'name': 'Consumer Complaints Procedure', 'completed': bool(self.complaints_procedure_file), 'category': 'compliance'})
        
        # Application Forms
        reqs.append({'name': 'Application Form (Schedule I)', 'completed': bool(self.application_form_schedule1), 'category': 'application'})
        reqs.append({'name': 'Application Form (Schedule II)', 'completed': bool(self.application_form_schedule2), 'category': 'application'})
        reqs.append({'name': 'Investigation Fee Payment', 'completed': self.investigation_fee_paid, 'category': 'application'})
        
        return reqs


class DirectorInformation(models.Model):
    #CBL-compliant director information
    
    registration = models.ForeignKey(CBLLenderRegistration, on_delete=models.CASCADE, related_name='directors')
    
    # Personal Information
    full_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    nationality = models.CharField(max_length=100)
    
    # Contact
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    physical_address = models.TextField()
    
    # Position
    is_chairman = models.BooleanField(default=False)
    is_executive = models.BooleanField(default=False)
    committee_memberships = models.JSONField(default=list, help_text="['Audit', 'Credit', 'Risk']")
    
    # Required Documents (Schedule III requirements)
    fit_proper_questionnaire = models.FileField(upload_to='directors/fit_proper/', null=True, blank=True)
    character_reference_1 = models.FileField(upload_to='directors/references/', null=True, blank=True)
    character_reference_2 = models.FileField(upload_to='directors/references/', null=True, blank=True)
    financial_reference_bank = models.FileField(upload_to='directors/bank_ref/', null=True, blank=True)
    schedule_iii_form = models.FileField(upload_to='directors/schedule3/', null=True, blank=True)
    id_passport_copy = models.FileField(upload_to='directors/ids/', null=True, blank=True)
    police_clearance = models.FileField(upload_to='directors/police/', null=True, blank=True)
    tax_clearance = models.FileField(upload_to='directors/tax/', null=True, blank=True)
    assets_liabilities_statement = models.FileField(upload_to='directors/financials/', null=True, blank=True)
    
    # Additional Information
    other_directorships = models.TextField(blank=True, help_text="List other MFI directorships (must be 0 for Tier 1/2)")
    qualifications = models.TextField(blank=True)
    experience_years = models.IntegerField(default=0)
    
    # Verification
    documents_complete = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_directors')
    
    def check_documents_complete(self):
        # Check if all required documents are uploaded
        required = [
            self.fit_proper_questionnaire,
            self.character_reference_1,
            self.character_reference_2,
            self.financial_reference_bank,
            self.schedule_iii_form,
            self.id_passport_copy,
            self.police_clearance,
            self.tax_clearance,
            self.assets_liabilities_statement,
        ]
        self.documents_complete = all(required)
        self.save()
        return self.documents_complete


class FinanceFunction(models.Model):
    # Finance Manager/Function requirements
    
    registration = models.OneToOneField(CBLLenderRegistration, on_delete=models.CASCADE, related_name='finance_function')
    
    # Person Details
    full_name = models.CharField(max_length=200)
    is_lia_member = models.BooleanField(default=False, help_text="Lesotho Institute of Accountants member")
    lia_membership_cert = models.FileField(upload_to='finance/lia/', null=True, blank=True)
    lia_practicing_cert = models.FileField(upload_to='finance/lia/', null=True, blank=True)
    
    # If outsourced
    is_outsourced = models.BooleanField(default=False)
    service_level_agreement = models.FileField(upload_to='finance/sla/', null=True, blank=True)
    
    # Standard documents (same as directors)
    fit_proper_questionnaire = models.FileField(upload_to='finance/fit_proper/', null=True, blank=True)
    character_reference_1 = models.FileField(upload_to='finance/references/', null=True, blank=True)
    character_reference_2 = models.FileField(upload_to='finance/references/', null=True, blank=True)
    financial_reference_bank = models.FileField(upload_to='finance/bank_ref/', null=True, blank=True)
    schedule_iii_form = models.FileField(upload_to='finance/schedule3/', null=True, blank=True)
    id_passport_copy = models.FileField(upload_to='finance/ids/', null=True, blank=True)
    police_clearance = models.FileField(upload_to='finance/police/', null=True, blank=True)
    tax_clearance = models.FileField(upload_to='finance/tax/', null=True, blank=True)
    assets_liabilities_statement = models.FileField(upload_to='finance/financials/', null=True, blank=True)


class ComplianceFunction(models.Model):
    #Compliance Officer/Function requirements
    
    registration = models.OneToOneField(CBLLenderRegistration, on_delete=models.CASCADE, related_name='compliance_function')
    
    # Person Details
    full_name = models.CharField(max_length=200)
    qualifications = models.TextField()
    
    # If outsourced
    is_outsourced = models.BooleanField(default=False)
    service_level_agreement = models.FileField(upload_to='compliance/sla/', null=True, blank=True)
    
    # Standard documents (same as directors)
    fit_proper_questionnaire = models.FileField(upload_to='compliance/fit_proper/', null=True, blank=True)
    character_reference_1 = models.FileField(upload_to='compliance/references/', null=True, blank=True)
    character_reference_2 = models.FileField(upload_to='compliance/references/', null=True, blank=True)
    financial_reference_bank = models.FileField(upload_to='compliance/bank_ref/', null=True, blank=True)
    schedule_iii_form = models.FileField(upload_to='compliance/schedule3/', null=True, blank=True)
    id_passport_copy = models.FileField(upload_to='compliance/ids/', null=True, blank=True)
    police_clearance = models.FileField(upload_to='compliance/police/', null=True, blank=True)
    tax_clearance = models.FileField(upload_to='compliance/tax/', null=True, blank=True)
    assets_liabilities_statement = models.FileField(upload_to='compliance/financials/', null=True, blank=True)



class LenderComplianceRegistration(models.Model):
    # Track lender through registration journey
    
    LENDER_TYPES = [
        ('individual', 'Individual Lender'),
        ('small_mfi', 'Small MFI (Simplified License)'),
        ('full_mfi', 'Full MFI License'),
        ('peer_to_peer', 'Peer-to-Peer (No License)'),
    ]
    
    REGISTRATION_STAGES = [
        ('assessment', 'Initial Assessment'),
        ('document_collection', 'Document Collection'),
        ('application_prep', 'Application Preparation'),
        ('cbl_submission', 'CBL Submission'),
        ('pending_approval', 'Pending CBL Approval'),
        ('interim_operations', 'Interim Operations'),
        ('approved', 'Approved & Operating'),
        ('rejected', 'Rejected'),
    ]
    
    # Basic info
    applicant = models.ForeignKey(User, on_delete=models.CASCADE)
    lender_type = models.CharField(max_length=50, choices=LENDER_TYPES)
    company_name = models.CharField(max_length=200)
    
    # Capital assessment
    available_capital = models.DecimalField(max_digits=12, decimal_places=2)
    capital_source = models.TextField()
    
    # Registration tracking
    current_stage = models.CharField(max_length=50, choices=REGISTRATION_STAGES, default='assessment')
    started_at = models.DateTimeField(auto_now_add=True)
    cbl_submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Compliance requirements
    has_board = models.BooleanField(default=False)
    has_compliance_officer = models.BooleanField(default=False)
    has_business_plan = models.BooleanField(default=False)
    has_aml_procedures = models.BooleanField(default=False)
    
    # CBL interaction
    cbl_application_number = models.CharField(max_length=100, blank=True)
    cbl_feedback = models.TextField(blank=True)
    
    # Platform relationship
    operating_under_platform = models.BooleanField(default=False)
    interim_lending_approved = models.BooleanField(default=False)
    
    def get_completion_percentage(self):
        #Calculate how complete the application is
        required_fields = self.get_required_fields()
        completed = sum(1 for field in required_fields if getattr(self, field))
        return (completed / len(required_fields)) * 100 if required_fields else 0
    
    def get_required_fields(self):
        #Return required fields based on lender type
        if self.lender_type == 'individual':
            return ['capital_source', 'applicant']
        elif self.lender_type == 'small_mfi':
            return ['has_board', 'has_compliance_officer', 'has_business_plan', 'has_aml_procedures']
        elif self.lender_type == 'full_mfi':
            return ['has_board', 'has_compliance_officer', 'has_business_plan', 'has_aml_procedures']
        return []


class CBLDocument(models.Model):
    #Store documents needed for CBL application
    
    DOCUMENT_TYPES = [
        # Personal documents
        ('id_document', 'National ID / Passport'),
        ('proof_of_address', 'Proof of Address'),
        ('tax_clearance', 'Tax Clearance Certificate'),
        ('police_clearance', 'Police Clearance Certificate'),
        
        # Business documents
        ('company_registration', 'Company Registration Certificate'),
        ('memorandum', 'Memorandum & Articles of Association'),
        ('business_plan', 'Business Plan'),
        ('financial_projections', 'Financial Projections (3 years)'),
        
        # Compliance documents
        ('aml_policy', 'AML/CFT Policy Manual'),
        ('operations_manual', 'Operations Manual'),
        ('board_resolution', 'Board Resolution'),
        ('source_of_funds', 'Source of Funds Declaration'),
        
        # Capital proof
        ('bank_statement', 'Bank Statement (Capital Proof)'),
        ('audited_financials', 'Audited Financial Statements'),
        
        # Team documents
        ('board_cvs', 'Board Member CVs'),
        ('management_cvs', 'Management Team CVs'),
        ('org_structure', 'Organizational Structure Chart'),
    ]
    
    registration = models.ForeignKey(CBLLenderRegistration, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='lender_registration/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_documents')
    notes = models.TextField(blank=True)


class ComplianceRequirement(models.Model):
    #Track individual compliance requirements
    
    REQUIREMENT_CATEGORIES = [
        ('capital', 'Capital Requirements'),
        ('governance', 'Governance'),
        ('documentation', 'Documentation'),
        ('systems', 'Systems & Technology'),
        ('personnel', 'Personnel'),
        ('compliance', 'Compliance Framework'),
    ]
    
    registration = models.ForeignKey(CBLLenderRegistration, on_delete=models.CASCADE, related_name='requirements')
    category = models.CharField(max_length=50, choices=REQUIREMENT_CATEGORIES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    is_mandatory = models.BooleanField(default=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    evidence = models.FileField(upload_to='compliance_evidence/', null=True, blank=True)
"""
