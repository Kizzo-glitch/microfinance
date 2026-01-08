from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from django.utils import timezone
from uuid import uuid4
from django.conf import settings

from lenders.models import LenderProfile

user = settings.AUTH_USER_MODEL


# ================================
# COMPLIANCE PROFILE (Institutional)
# ================================

class ComplianceProfile(models.Model):
    """
    Top-level compliance record for a lender.
    Tracks licensing status, CBL reference, and overall progress.
    """
    lender = models.OneToOneField(LenderProfile, on_delete=models.CASCADE, related_name='compliance')
    
    # CBL Application Metadata
    cbl_application_reference = models.CharField(max_length=100, blank=True, help_text="CBL-assigned application reference")
    application_submitted_at = models.DateTimeField(null=True, blank=True)
    license_issued_at = models.DateTimeField(null=True, blank=True)
    cbl_license_number = models.CharField(max_length=100, blank=True)
    cbl_license_expiry = models.DateField(null=True, blank=True)

    # Application Stage
    STAGE_CHOICES = [
        ('not_started', 'Not Started'),
        ('document_gathering', 'Gathering Documents'),
        ('fit_proper_pending', 'Fit & Proper Pending'),
        ('submitted', 'Submitted to CBL'),
        ('under_review', 'CBL Under Review'),
        ('licensed', 'Licensed'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]
    current_stage = models.CharField(max_length=30, choices=STAGE_CHOICES, default='not_started')

    # Required Institutional Documents (Per Checklist)
    schedule_i = models.FileField(upload_to='compliance/schedule/', blank=True, null=True)
    schedule_ii = models.FileField(upload_to='compliance/schedule/', blank=True, null=True)  
    tax_clearance_institution = models.FileField(upload_to='compliance/tax/', blank=True, null=True)
   

    # Business Plan & Financials
    business_plan = models.FileField(upload_to='compliance/business_plans/', blank=True, null=True, help_text="Required for Tier 1 & 2")
    audited_financials = models.FileField(upload_to='compliance/audited_financials/', blank=True, null=True, help_text="Required for Tier 1 & 2")
    financial_statements_certified = models.FileField(upload_to='compliance/certified_statements/', blank=True, null=True, help_text="For Tier 3")
    capital_commitment_letter = models.FileField(upload_to='compliance/capital/', blank=True, null=True)
    bank_statements_capital = models.FileField(upload_to='compliance/bank_statements/', blank=True, null=True)

    # Governance & Policies
    risk_management_manual = models.FileField(upload_to='compliance/policies/', blank=True, null=True)
    aml_cft_manual = models.FileField(upload_to='compliance/policies/', blank=True, null=True)
    complaints_procedure = models.FileField(upload_to='compliance/policies/', blank=True, null=True)

    # Regulatory Submissions
    
    memorandum_articles = models.FileField(upload_to='compliance/legal/', blank=True, null=True)
    home_supervisor_consent = models.FileField(upload_to='compliance/foreign/', blank=True, null=True)  # For foreign entities

    # Board & Committee Evidence
    board_resolution_for_licensing = models.FileField(upload_to='compliance/board/', blank=True, null=True)
    board_list_with_terms = models.FileField(upload_to='compliance/board/', blank=True, null=True)
    credit_committee_terms = models.FileField(upload_to='compliance/committees/', blank=True, null=True, help_text="Tier 1 only")
    internal_audit_charter = models.FileField(upload_to='compliance/audit/', blank=True, null=True, help_text="Tier 1 & 2")

    # CBL Fee Payment (Optional tracking)
    investigation_fee_paid = models.BooleanField(default=False)
    investigation_fee_proof = models.FileField(
        upload_to='compliance/payments/', 
        null=True, 
        blank=True,
        help_text="Upload the bank transfer/deposit slip"
    )
    date_paid = models.DateTimeField(null=True, blank=True)
    registration_fee_paid = models.BooleanField(default=False)

    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def update_stage(self):
        """
        Evaluates current data and moves the application stage forward automatically.
        """
        # 1. Base check: Are institutional docs started?
        has_docs = any([self.aml_cft_manual, self.complaints_procedure, self.tax_clearance_institution])
        personnel_count = self.lender.personnel.count()

        if self.current_stage == 'not_started' and has_docs:
            self.current_stage = 'document_gathering'

        # 2. Transition to Fit & Proper if docs are in and personnel are being added
        if self.current_stage == 'document_gathering' and personnel_count > 0:
            self.current_stage = 'fit_proper_pending'

        # 3. Transition to 'Submitted' only happens via the POST button on the dashboard
        # so we don't automate that here.

        self.save(update_fields=['current_stage'])
    
    
    """
    def update_stage(self):
        
        # 1. If we have at least one document but aren't finished
        if self.current_stage == 'not_started':
            self.current_stage = 'document_gathering'
        
        # 2. If all core docs are in, but personnel is missing (Fit & Proper)
        # This logic matches your service progress logic
        core_docs_submitted = all([self.aml_cft_manual, self.complaints_procedure, self.tax_clearance_institution])
        
        if core_docs_submitted and self.current_stage == 'document_gathering':
            # Check if they have at least 1 personnel member
            if self.lender.personnel.exists():
                self.current_stage = 'fit_proper_pending'
            else:
                # Still gathering institutional docs or waiting for first personnel
                pass

        self.save(update_fields=['current_stage'])
    """


    def __str__(self):
        return f"Compliance: {self.lender.company_name}"

    @property
    def is_licensed(self):
        return self.current_stage == 'licensed' and self.cbl_license_number

    @property
    def license_expiry_warning(self):
        if not self.cbl_license_expiry:
            return False
        return (self.cbl_license_expiry - timezone.now().date()).days <= 60


# ================================
# KEY PERSONNEL (Directors, Officers)
# ================================

PERSONNEL_ROLE_CHOICES = [
    ('director', 'Director'),
    ('ceo', 'CEO / Managing Director'),
    ('finance_officer', 'Finance Officer'),
    ('compliance_officer', 'Compliance Officer'),
]

class PersonnelProfile(models.Model):
    """
    Captures CBL-mandated info for directors and key officers.
    Mirrors Schedule III and Fit & Proper Questionnaire.
    """
    lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='personnel')
    role = models.CharField(max_length=20, choices=PERSONNEL_ROLE_CHOICES)
    
    # Personal Details (Schedule III + Fit & Proper)
    full_name = models.CharField(max_length=200, help_text="No initials – full legal name")
    nationality = models.CharField(max_length=100)
    country_of_residence = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    place_of_birth = models.CharField(max_length=100)
    id_or_passport_number = models.CharField(max_length=50, blank=True)

    # Addresses
    business_address = models.TextField(blank=True)
    residential_address = models.TextField(blank=True)

    # Professional Info
    professional_qualifications = models.TextField(blank=True, help_text="Degrees, certificates, memberships")
    occupation_history = models.TextField(blank=True, help_text="Last 10 years of employment")
    employment_history_10_years = models.TextField(blank=True, help_text="Past 10 years of employment with reasons for leaving")

    # Business Affiliations
    other_affiliations = models.TextField(blank=True, help_text="Directorships, partnerships, >5% shareholdings")
    family_business_affiliations = models.TextField(blank=True, help_text="Spouse, children, parents, siblings")

    # Declarations (Boolean + explanations)
    ever_disqualified = models.BooleanField(default=False)
    disqualification_details = models.TextField(blank=True)

    legal_proceedings = models.BooleanField(default=False)
    legal_proceedings_details = models.TextField(blank=True)

    criminal_conviction = models.BooleanField(default=False)
    criminal_conviction_details = models.TextField(blank=True)

    bankruptcy = models.BooleanField(default=False)
    bankruptcy_details = models.TextField(blank=True)

    dismissed_or_resigned = models.BooleanField(default=False)
    dismissal_details = models.TextField(blank=True)

    # Fit & Proper Submission Status
    fit_proper_questionnaire_submitted = models.BooleanField(default=False)
    schedule_iii_submitted = models.BooleanField(default=False)

    # Required Documents (as per Schedule III)
    police_clearance = models.FileField(upload_to='compliance/personnel/police/', blank=True, null=True)
    tax_clearance = models.FileField(upload_to='compliance/personnel/tax/', blank=True, null=True)
    assets_liabilities_statement = models.FileField(upload_to='compliance/personnel/financials/', blank=True, null=True)
    character_references = models.FileField(upload_to='compliance/personnel/references/', blank=True, null=True, help_text="Two notarized letters")
    bank_references = models.FileField(upload_to='compliance/personnel/bank_refs/', blank=True, null=True, help_text="Two bank reference letters")
    id_copy = models.FileField(upload_to='compliance/personnel/id/', blank=True, null=True, help_text="Certified copy of ID or passport")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_complete(self):
        """Checks if all mandatory files and declarations are present."""
        required_files = [
            self.police_clearance, self.tax_clearance, self.id_copy,
            self.assets_liabilities_statement, self.character_references, self.bank_references
        ]
        # Check if all files exist and both questionnaires are marked as submitted
        files_ok = all(bool(f) for f in required_files)
        return files_ok and self.fit_proper_questionnaire_submitted and self.schedule_iii_submitted

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()}) - {self.lender.company_name}"
    
    @property
    def status(self):
        """Returns a dict with status label and a CSS class for badges."""
        if self.fit_proper_questionnaire_submitted and self.schedule_iii_submitted:
            # Check if they also uploaded all documents
            required_files = [self.police_clearance, self.tax_clearance, self.id_copy]
            if all(bool(f) for f in required_files):
                return {'label': 'Finalized', 'class': 'success'}
            return {'label': 'Questionnaire Done (Docs Pending)', 'class': 'info'}
        
        return {'label': 'Draft', 'class': 'warning'}


# ================================
# COMPLIANCE DOCUMENT TRACKER
# ================================

DOCUMENT_TYPE_CHOICES = [
    # Institutional
    ('schedule_i', 'Schedule I - License Application'),
    ('schedule_ii', 'Schedule II - Information Sheet'),
    ('business_plan', 'Business Plan'),
    ('audited_financials', 'Audited Financial Statements'),
    ('financial_statements_certified', 'Certified Financial Statements (Tier 3)'),
    ('capital_proof', 'Proof of Capital'),
    ('board_resolution', 'Board Resolution for Licensing'),
    ('memorandum_articles', 'Memorandum & Articles of Association'),
    ('tax_clearance_institution', 'Institution Tax Clearance'),
    ('risk_manual', 'Risk Management Manual'),
    ('aml_manual', 'AML/CFT Manual'),
    ('complaints_procedure', 'Consumer Complaints Procedure'),
    
    # Personnel (generic – linked via PersonnelProfile instead)
    # But kept for flexibility if needed
]

class ComplianceDocument(models.Model):
    """
    Optional: for tracking institutional documents not covered above.
    Use mainly for non-personnel, non-core files.
    """
    lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='compliance_documents')
    doc_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(upload_to='compliance/docs/')
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(user, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.lender.company_name}"


# ================================
# COMPLIANCE CHECKLIST ITEM (Dynamic)
# ================================

class ComplianceChecklistItem(models.Model):
    """
    Tracks completion status of each CBL requirement per lender.
    Enables dynamic UI checklists based on tier.
    """
    lender = models.ForeignKey(LenderProfile, on_delete=models.CASCADE, related_name='checklist_items')
    requirement_key = models.CharField(max_length=100)  # e.g. 'fit_proper_directors', 'aml_manual'
    description = models.CharField(max_length=255)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    evidence_file = models.FileField(upload_to='compliance/checklist_evidence/', blank=True, null=True)
    
    class Meta:
        unique_together = ('lender', 'requirement_key')

    def __str__(self):
        return f"{self.lender.company_name} - {self.description}: {'✅' if self.completed else '❌'}"


# ================================
# SIGNALS (Optional – Add to apps.py or signals.py)
# ================================

# You may want to auto-create ComplianceProfile when LenderProfile is created
# and auto-populate checklist items based on cbl_tier.
