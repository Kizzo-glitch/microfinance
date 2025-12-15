from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import (CBLRegistration, KeyPersonnel, 
    ComplianceDocument, ComplianceChecklist
)
from lenders.models import LenderProfile




@receiver(post_save, sender=CBLRegistration)
def generate_compliance_checklist(sender, instance, created, **kwargs):
    """Auto-generate compliance checklist when registration is created"""
    if created:
        generate_tier_requirements(instance)


def generate_tier_requirements(registration):
    """Generate checklist items based on tier"""
    
    tier = registration.target_tier
    items = []
    
    # Common requirements for all tiers
    common = [
        ('company', 'Company Registration Certificate', True, 'critical'),
        ('company', 'Memorandum & Articles of Association', True, 'critical'),
        ('company', 'Tax Clearance Certificate', True, 'high'),
        ('capital', 'Proof of Minimum Capital', True, 'critical'),
        ('compliance', 'AML/CFT Policy Manual', True, 'critical'),
        ('compliance', 'Consumer Complaints Procedure', True, 'high'),
        ('application', 'Application Form (Schedule I)', True, 'critical'),
        ('application', 'Application Form (Schedule II)', True, 'critical'),
        ('application', 'Investigation Fee Payment', True, 'critical'),
    ]
    
    for category, req, mandatory, priority in common:
        items.append({
            'category': category,
            'requirement': req,
            'is_mandatory': mandatory,
            'priority': priority,
            'applies_to_tier1': True,
            'applies_to_tier2': True,
            'applies_to_tier3': True,
        })
    
    # Tier 1 & 2 specific
    tier12_specific = [
        ('documentation', 'Detailed Business Plan (3-5 years)', True, 'high'),
        ('documentation', 'Audited Financial Statements', True, 'high'),
        ('governance', 'Board of Directors (5+ members)', True, 'critical'),
        ('governance', 'Finance Manager/CFO Appointment', True, 'high'),
        ('governance', 'Compliance Officer Appointment', True, 'high'),
        ('compliance', 'Risk Management Manual', True, 'high'),
    ]
    
    for category, req, mandatory, priority in tier12_specific:
        items.append({
            'category': category,
            'requirement': req,
            'is_mandatory': mandatory,
            'priority': priority,
            'applies_to_tier1': True,
            'applies_to_tier2': True,
            'applies_to_tier3': False,
        })
    
    # Tier 1 only
    tier1_only = [
        ('governance', 'Internal Audit Committee', True, 'high'),
        ('governance', 'Board Credit Committee (3+ members)', True, 'high'),
        ('governance', 'Internal Audit Function', True, 'high'),
        ('compliance', 'Liquidity Management Policy', True, 'medium'),
    ]
    
    for category, req, mandatory, priority in tier1_only:
        items.append({
            'category': category,
            'requirement': req,
            'is_mandatory': mandatory,
            'priority': priority,
            'applies_to_tier1': True,
            'applies_to_tier2': False,
            'applies_to_tier3': False,
        })
    
    # Tier 3 specific
    tier3_specific = [
        ('documentation', 'Certified Accountant Statement', True, 'high'),
        ('governance', 'Board of Directors (3+ members)', True, 'high'),
    ]
    
    for category, req, mandatory, priority in tier3_specific:
        items.append({
            'category': category,
            'requirement': req,
            'is_mandatory': mandatory,
            'priority': priority,
            'applies_to_tier1': False,
            'applies_to_tier2': False,
            'applies_to_tier3': True,
        })
    
    # Director requirements (per director)
    director_docs = [
        ('Fit & Proper Assessment Questionnaire', True),
        ('Two Character Reference Letters', True),
        ('Bank/Financial Reference', True),
        ('Schedule III Form', True),
        ('ID/Passport Copy', True),
        ('Police Clearance Certificate', True),
        ('Personal Tax Clearance', True),
        ('Statement of Assets & Liabilities', True),
    ]
    
    # Create checklist items
    order = 0
    for item in items:
        tier_applies = False
        if tier == 'tier1' and item['applies_to_tier1']:
            tier_applies = True
        elif tier == 'tier2' and item['applies_to_tier2']:
            tier_applies = True
        elif tier == 'tier3' and item['applies_to_tier3']:
            tier_applies = True
        
        if tier_applies:
            ComplianceChecklist.objects.create(
                registration=registration,
                category=item['category'],
                requirement=item['requirement'],
                is_mandatory=item['is_mandatory'],
                priority=item['priority'],
                applies_to_tier1=item['applies_to_tier1'],
                applies_to_tier2=item['applies_to_tier2'],
                applies_to_tier3=item['applies_to_tier3'],
                order=order
            )
            order += 1


@receiver(post_save, sender=KeyPersonnel)
def update_registration_counts(sender, instance, **kwargs):
    """Update registration governance counts when personnel changes"""
    registration = instance.registration
    
    # Update board size
    registration.board_size = registration.key_personnel.filter(
        role__in=['director', 'chairman']
    ).count()
    
    # Check for specific roles
    registration.has_finance_manager = registration.key_personnel.filter(
        role__in=['finance_manager', 'cfo']
    ).exists()
    
    registration.has_compliance_officer = registration.key_personnel.filter(
        role='compliance_officer'
    ).exists()
    
    registration.save(update_fields=[
        'board_size', 'has_finance_manager', 'has_compliance_officer'
    ])


@receiver(post_save, sender=ComplianceDocument)
def check_document_completion(sender, instance, **kwargs):
    """Check if document upload completes any requirements"""
    
    # Update personnel document status
    if instance.key_personnel:
        instance.key_personnel.check_documents_complete()
    
    # Mark checklist items as complete
    if instance.cbl_registration and instance.status == 'approved':
        # Map document types to requirements
        doc_req_map = {
            'company_registration': 'Company Registration Certificate',
            'aml_manual': 'AML/CFT Policy Manual',
            'business_plan': 'Detailed Business Plan',
            'risk_manual': 'Risk Management Manual',
        }
        
        if instance.document_type in doc_req_map:
            req_name = doc_req_map[instance.document_type]
            ComplianceChecklist.objects.filter(
                registration=instance.cbl_registration,
                requirement__icontains=req_name,
                is_completed=False
            ).update(
                is_completed=True,
                completed_at=timezone.now(),
                evidence_document=instance
            )


@receiver(pre_save, sender=LenderProfile)
def update_verification_timestamp(sender, instance, **kwargs):
    """Update verified_at when status changes to verified"""
    if instance.pk:
        try:
            old_instance = LenderProfile.objects.get(pk=instance.pk)
            if (old_instance.verification_status != instance.verification_status 
                and instance.verification_status in ['verified', 'licensed']):
                instance.verified_at = timezone.now()
        except LenderProfile.DoesNotExist:
            pass