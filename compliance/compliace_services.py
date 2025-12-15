# services.py

from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta

from lenders.models import LenderProfile
from .models import (
     ComplianceDocument, CBLRegistration,
    OngoingComplianceReport
)



class ComplianceDashboardService:
    def __init__(self, lender_profile):
        self.lender = lender_profile
        self.registration = getattr(lender_profile, "cbl_registration", None)

    def get_dashboard_data(self):
        if not self.registration:
            return {
                "has_registration": False,
                "completion": 0,
                "stage": "Not Started",
                "missing": []
            }

        req_service = RequirementService(self.registration)
        reqs = req_service.get_requirements()

        missing = [r["name"] for r in reqs if not r["completed"]]

        return {
            "has_registration": True,
            "completion": req_service.completion_percentage(),
            "stage": self.registration.get_current_stage_display(),
            "missing": missing[:5],
        }




"""

class ComplianceDashboardService:
   
    #Aggregates compliance-related dashboard data for lenders.
   

    def __init__(self, lender_profile: LenderProfile):
        self.lender = lender_profile
        self.registration = getattr(lender_profile, 'cbl_registration', None)

    def get_summary(self):
        
        #Main entry point used by dashboards
        
        if not self.registration:
            return self._no_registration_summary()

        return {
            "has_registration": True,
            "current_stage": self.registration.current_stage,
            "stage_label": self.registration.get_current_stage_display(),
            "completion_percentage": self.registration.get_completion_percentage(),
            "missing_requirements": self.get_missing_requirements(),
            "next_action": self.get_next_action(),
            "is_submitted_to_cbl": self.registration.submitted_to_cbl,
            "approved": self.registration.approved,
        }

    def _no_registration_summary(self):
        return {
            "has_registration": False,
            "current_stage": None,
            "stage_label": "Not Started",
            "completion_percentage": 0,
            "missing_requirements": [],
            "next_action": "Start CBL Compliance Process",
            "is_submitted_to_cbl": False,
            "approved": False,
        }

    def get_missing_requirements(self):
        
        #Returns critical incomplete requirements
        
        requirements = self.registration.get_all_requirements()
        return [
            req for req in requirements
            if req["required"] and not req["completed"]
        ]

    def get_next_action(self):
        
        #Human-readable next step for UI
        
        stage = self.registration.current_stage

        stage_actions = {
            "initiated": "Complete Tier Assessment",
            "tier_assessment": "Provide Company Information",
            "company_info": "Add Directors & Key Personnel",
            "directors_info": "Set Up Governance Structures",
            "governance_setup": "Upload Required Documents",
            "document_collection": "Submit Documents for Review",
            "internal_review": "Await Platform Review",
            "cbl_submission": "Await CBL Review",
            "additional_info": "Respond to CBL Queries",
            "approved": "License Approved 🎉",
        }

        return stage_actions.get(stage, "Continue Compliance Process")
        """
"""
class ComplianceDashboardService:
    def __init__(self, lender_profile):
        self.lender = lender_profile

    def get_summary(self):
        try:
            registration = self.lender.cbl_registration
        except CBLRegistration.DoesNotExist:
            return {
                "has_registration": False,
                "completion": 0,
                "current_stage": None,
                "missing_critical": [],
                "next_action": "Start compliance registration"
            }

        requirements = registration.get_all_requirements()
        missing_critical = [
            r for r in requirements
            if r["required"] and not r["completed"]
        ]

        return {
            "has_registration": True,
            "completion": registration.get_completion_percentage(),
            "current_stage": registration.get_current_stage_display(),
            "missing_critical": missing_critical[:3],  # show top 3
            "next_action": self._next_action(registration),
            "registration": registration
        }

    def _next_action(self, registration):
        stage_actions = {
            "initiated": "Complete tier assessment",
            "company_info": "Complete company information",
            "directors_info": "Add directors & key personnel",
            "document_collection": "Upload required documents",
            "fee_payment": "Pay investigation fee",
            "internal_review": "Await internal review",
            "cbl_submission": "Await CBL review",
        }
        return stage_actions.get(registration.current_stage, "Continue compliance")
"""

class CBLRegistrationService:

    STAGE_URL_MAP = {
        'initiated': 'compliance:tier_selection',
        'tier_assessment': 'compliance:tier_selection',
        'company_info': 'compliance:company_info',
        'directors_info': 'compliance:directors',
        'governance_setup': 'compliance:governance',
        'document_collection': 'compliance:documents',
        'document_review': 'compliance:documents',
        'application_prep': 'compliance:review',
        'internal_review': 'compliance:review',
    }

    @classmethod
    def get_next_step_url(cls, registration):
        return cls.STAGE_URL_MAP.get(
            registration.current_stage,
            'compliance:dashboard'
        )


class ComplianceProgressService:
    """
    Computes progress, percentages, and summaries.
    """

    def __init__(self, registration):
        self.registration = registration

    def completion_percentage(self):
        return self.registration.get_completion_percentage()

    def status_badge(self):
        pct = self.completion_percentage()

        if pct == 100:
            return 'Complete'
        if pct >= 75:
            return 'Almost There'
        if pct >= 40:
            return 'In Progress'
        return 'Getting Started'

    def dashboard_snapshot(self):
        return {
            'percentage': self.completion_percentage(),
            'stage': self.registration.current_stage,
            'badge': self.status_badge(),
            'submitted_to_cbl': self.registration.submitted_to_cbl,
            'approved': self.registration.approved,
        }

class RequirementService:
    """
    Computes requirements & completion for a CBLRegistration
    """

    def __init__(self, registration):
        self.registration = registration
        self.lender = registration.lender_profile

    def get_requirements(self):
        r = []

        # Company info
        r += [
            self._req("Company Registration", bool(self.lender.registration_number)),
            self._req("Tax Clearance", bool(self.lender.tax_identification_number)),
            self._req("Capital Proof", self.registration.capital_proof_verified),
        ]

        # Business plan
        if self.registration.business_plan_required:
            r.append(
                self._req("Business Plan", self.registration.business_plan_approved)
            )

        # Financials
        if self.registration.requires_audited_financials:
            r.append(
                self._req("Audited Financials", self.registration.financials_verified)
            )

        # Directors
        min_board = self.lender.minimum_board_size
        if min_board > 0:
            actual = self.registration.key_personnel.filter(role="director").count()
            r.append(
                self._req(
                    f"Board Directors ({min_board}+)",
                    actual >= min_board
                )
            )

        # Committees (Tier 1)
        if self.registration.target_tier == "tier1":
            r += [
                self._req("Audit Committee", self.registration.has_audit_committee),
                self._req("Credit Committee", self.registration.has_credit_committee),
            ]

        # Officers
        if self.registration.target_tier in ["tier1", "tier2"]:
            r += [
                self._req("Finance Manager", self.registration.has_finance_manager),
                self._req("Compliance Officer", self.registration.has_compliance_officer),
            ]

        # Policies
        r.append(self._req("AML Manual", self.registration.aml_manual_approved))
        if self.registration.target_tier in ["tier1", "tier2"]:
            r.append(self._req("Risk Manual", self.registration.risk_manual_approved))

        r.append(
            self._req(
                "Complaints Procedure",
                self.registration.complaints_procedure_generated
            )
        )

        # Fees
        r.append(
            self._req(
                "Investigation Fee",
                self.registration.investigation_fee_paid
            )
        )

        return r

    def completion_percentage(self):
        reqs = self.get_requirements()
        if not reqs:
            return 0
        completed = sum(1 for r in reqs if r["completed"])
        return int((completed / len(reqs)) * 100)

    def _req(self, name, completed):
        return {
            "name": name,
            "completed": completed
        }


class RequirementEvaluatorService:
    """
    Evaluates compliance requirements for a CBLRegistration
    """

    def __init__(self, registration):
        self.registration = registration

    def all_requirements(self):
        return self.registration.get_all_requirements()

    def missing_requirements(self):
        return [
            r for r in self.all_requirements()
            if r['required'] and not r['completed']
        ]

    def is_stage_complete(self):
        return len(self.missing_requirements()) == 0



class ComplianceWorkflowService:
    """
    Controls movement between CBL stages.
    """

    STAGE_SEQUENCE = [
        'initiated',
        'tier_assessment',
        'company_info',
        'directors_info',
        'governance_setup',
        'document_collection',
        'document_review',
        'application_prep',
        'fee_payment',
        'internal_review',
        'cbl_submission',
        'cbl_review',
        'approved',
    ]

    def __init__(self, registration):
        self.registration = registration

    def can_advance(self):
        evaluator = RequirementEvaluatorService(self.registration)
        return evaluator.is_stage_complete(self.registration.current_stage)

    def advance(self):
        if not self.can_advance():
            return False

        idx = self.STAGE_SEQUENCE.index(self.registration.current_stage)
        if idx < len(self.STAGE_SEQUENCE) - 1:
            self.registration.current_stage = self.STAGE_SEQUENCE[idx + 1]
            self.registration.save()
            return True

        return False




class DocumentStatusService:
    """
    Evaluates document completeness and health.
    """

    def __init__(self, registration):
        self.registration = registration

    def documents_by_category(self):
        docs = self.registration.documents.select_related()
        grouped = {}
        for doc in docs:
            grouped.setdefault(doc.category, []).append(doc)
        return grouped

    def missing_documents(self):
        missing = []
        for req in self.registration.get_all_requirements():
            if req['category'] in ['documentation', 'compliance'] and not req['completed']:
                missing.append(req['name'])
        return missing

    def expired_documents(self):
        return ComplianceDocument.objects.filter(
            cbl_registration=self.registration,
            expiry_date__lt=timezone.now().date(),
            is_current=True
        )



class ComplianceDashboardService:

    def __init__(self, registration):
        self.registration = registration
        self.progress = ComplianceProgressService(registration)
        self.docs = DocumentStatusService(registration)

    def dashboard_data(self):
        return {
            'current_stage': self.registration.current_stage,
            'completion_percentage': self.progress.completion_percentage(),
            'missing_documents': self.docs.missing_company_documents(),
            'pending_personnel': self.docs.personnel_with_missing_docs(),
            'can_advance': self.progress.can_advance(),
        }


class TierAssessmentService:
    #Service to assess and recommend appropriate CBL tier
    
    TIER_THRESHOLDS = {
        'tier1': {
            'min_capital': Decimal('10000000'),
            'accepts_deposits': True,
            'min_board': 5,
        },
        'tier2': {
            'min_capital': Decimal('10000000'),  # or public debt
            'min_assets': Decimal('10000000'),
            'accepts_deposits': False,
            'min_board': 5,
        },
        'tier3': {
            'max_assets': Decimal('10000000'),
            'accepts_deposits': False,
            'min_board': 3,
        },
        'individual': {
            'max_capital': Decimal('500000'),
            'operates_under_platform': True,
        },
    }
    
    @classmethod
    def assess(cls, capital, assets=None, wants_deposits=False, 
               has_public_debt=False, has_team=False):
        
        #Assess appropriate tier based on criteria
        
        #Returns: tuple (tier, reasoning, requirements)
        
        if wants_deposits:
            return (
                'tier1',
                'Deposit-taking requires Tier 1 license.',
                cls.get_tier_requirements('tier1')
            )
        
        if assets and assets >= Decimal('10000000'):
            return (
                'tier2',
                f'Assets of M {assets:,.2f} qualify for Tier 2.',
                cls.get_tier_requirements('tier2')
            )
        
        if has_public_debt:
            return (
                'tier2',
                'Public debt instruments require Tier 2 license.',
                cls.get_tier_requirements('tier2')
            )
        
        if capital >= Decimal('500000') and has_team:
            return (
                'tier3',
                'Suitable for Tier 3 (simplified requirements).',
                cls.get_tier_requirements('tier3')
            )
        
        return (
            'individual',
            'Recommended to operate under platform umbrella.',
            cls.get_tier_requirements('individual')
        )
    
    @classmethod
    def get_tier_requirements(cls, tier):
        #Get detailed requirements for a tier
        
        requirements = {
            'tier1': {
                'capital': 'Not specified (highest)',
                'board_members': 5,
                'committees': ['Audit', 'Credit', 'Risk'],
                'management': ['CEO', 'CFO', 'Compliance Officer', 'Risk Officer'],
                'external_audit': True,
                'business_plan': True,
                'audited_financials': True,
                'estimated_time': '6-12 months',
                'estimated_cost': 'M 500,000+',
            },
            'tier2': {
                'capital': 'M 10,000,000+ in assets',
                'board_members': 5,
                'committees': [],
                'management': ['CEO', 'Finance Manager', 'Compliance Officer'],
                'external_audit': True,
                'business_plan': True,
                'audited_financials': True,
                'estimated_time': '4-8 months',
                'estimated_cost': 'M 200,000+',
            },
            'tier3': {
                'capital': 'Below M 10,000,000 assets',
                'board_members': 3,
                'committees': [],
                'management': ['Manager'],
                'external_audit': False,
                'business_plan': False,
                'audited_financials': False,
                'estimated_time': '2-4 months',
                'estimated_cost': 'M 50,000+',
            },
            'individual': {
                'capital': 'M 50,000 - M 500,000',
                'board_members': 0,
                'committees': [],
                'management': [],
                'external_audit': False,
                'business_plan': False,
                'audited_financials': False,
                'estimated_time': '2-4 weeks',
                'estimated_cost': 'M 5,000 setup',
                'note': 'Operates under platform license',
            },
        }
        
        return requirements.get(tier, {})


class RegistrationWorkflowService:
    #Manage the CBL registration workflow
    
    STAGE_TRANSITIONS = {
        'initiated': ['tier_assessment'],
        'tier_assessment': ['company_info'],
        'company_info': ['directors_info'],
        'directors_info': ['governance_setup'],
        'governance_setup': ['document_collection'],
        'document_collection': ['document_review'],
        'document_review': ['application_prep', 'document_collection'],  # can go back
        'application_prep': ['fee_payment'],
        'fee_payment': ['internal_review'],
        'internal_review': ['cbl_submission', 'document_collection'],
        'cbl_submission': ['cbl_review'],
        'cbl_review': ['additional_info', 'approved', 'rejected'],
        'additional_info': ['cbl_submission'],
        'approved': [],
        'rejected': [],
        'withdrawn': [],
    }
    
    def __init__(self, registration):
        self.registration = registration
    
    def can_advance_to(self, stage):
        #Check if transition to stage is allowed
        current = self.registration.current_stage
        allowed = self.STAGE_TRANSITIONS.get(current, [])
        return stage in allowed
    
    def advance_stage(self, target_stage, user=None):
        #Advance to specified stage if allowed and requirements met
        
        if not self.can_advance_to(target_stage):
            raise ValidationError(
                f"Cannot transition from {self.registration.current_stage} to {target_stage}"
            )
        
        # Check stage-specific requirements
        requirements_met, missing = self.check_stage_requirements(target_stage)
        if not requirements_met:
            raise ValidationError(f"Requirements not met: {', '.join(missing)}")
        
        self.registration.current_stage = target_stage
        self.registration.save()
        
        # Log the transition
        self.log_stage_change(target_stage, user)
        
        return True
    
    def check_stage_requirements(self, stage):
        #Check if requirements for entering a stage are met
        
        reg = self.registration
        missing = []
        
        if stage == 'directors_info':
            if not reg.lender_profile.company_name:
                missing.append('Company name')
            if not reg.lender_profile.registration_number:
                missing.append('Company registration number')
        
        elif stage == 'governance_setup':
            min_directors = reg.lender_profile.minimum_board_size
            actual = reg.key_personnel.filter(role__in=['director', 'chairman']).count()
            if actual < min_directors:
                missing.append(f'At least {min_directors} directors required')
        
        elif stage == 'document_review':
            incomplete = reg.checklist_items.filter(
                is_mandatory=True,
                is_completed=False,
                category='documentation'
            ).count()
            if incomplete > 0:
                missing.append(f'{incomplete} mandatory documents pending')
        
        elif stage == 'cbl_submission':
            if not reg.investigation_fee_paid:
                missing.append('Investigation fee not paid')
            
            completion = reg.get_completion_percentage()
            if completion < 100:
                missing.append(f'Application only {completion}% complete')
        
        return len(missing) == 0, missing
    
    def log_stage_change(self, stage, user):
        #Log stage transition for audit trail
        # Implement audit logging here
        pass
    
    def get_next_actions(self):
        #Get list of actions needed to progress#
        
        reg = self.registration
        actions = []
        
        # Check incomplete checklist items
        incomplete = reg.checklist_items.filter(
            is_mandatory=True,
            is_completed=False
        ).order_by('priority', 'order')[:5]
        
        for item in incomplete:
            actions.append({
                'type': 'requirement',
                'priority': item.priority,
                'title': item.requirement,
                'category': item.category,
            })
        
        # Check personnel documents
        for personnel in reg.key_personnel.filter(documents_complete=False):
            actions.append({
                'type': 'personnel_docs',
                'priority': 'high',
                'title': f'Complete documents for {personnel.full_name}',
                'category': 'personnel',
            })
        
        return actions


class OngoingComplianceService:
    #Manage ongoing compliance requirements for licensed lenders
    
    REPORT_SCHEDULE = {
        'quarterly_prudential': {
            'frequency': 'quarterly',
            'due_days_after_period': 30,
            'applies_to': ['tier1', 'tier2', 'tier3'],
        },
        'annual_return': {
            'frequency': 'annually',
            'due_days_after_period': 90,
            'applies_to': ['tier1', 'tier2', 'tier3'],
        },
        'external_audit': {
            'frequency': 'annually',
            'due_days_after_period': 120,
            'applies_to': ['tier1', 'tier2'],
        },
        'credit_bureau': {
            'frequency': 'monthly',
            'due_days_after_period': 15,
            'applies_to': ['tier1', 'tier2', 'tier3'],
        },
    }
    
    def __init__(self, lender_profile):
        self.lender = lender_profile
    
    def generate_scheduled_reports(self):
        #Generate upcoming report requirements
        
        today = timezone.now().date()
        
        for report_type, config in self.REPORT_SCHEDULE.items():
            if self.lender.cbl_tier not in config['applies_to']:
                continue
            
            # Check if report already exists for current period
            # Generate if not
            pass
    
    def get_upcoming_deadlines(self, days=60):
        #Get compliance deadlines within X days
        
        cutoff = timezone.now().date() + timedelta(days=days)
        
        return OngoingComplianceReport.objects.filter(
            lender_profile=self.lender,
            due_date__lte=cutoff,
            status__in=['pending', 'in_progress']
        ).order_by('due_date')
    
    def get_overdue_reports(self):
        #Get overdue compliance reports
        
        return OngoingComplianceReport.objects.filter(
            lender_profile=self.lender,
            due_date__lt=timezone.now().date(),
            status__in=['pending', 'in_progress']
        )
    
    def generate_prudential_report_data(self, period_end):
        #Auto-generate prudential report data from loan system
        
        # This would integrate with your loan models
        data = {
            'reporting_period_end': period_end.isoformat(),
            'total_assets': 0,
            'total_liabilities': 0,
            'capital': 0,
            'loan_portfolio': {
                'total_loans': 0,
                'performing': 0,
                'par_30': 0,  # Portfolio at Risk 30 days
                'par_90': 0,
                'written_off': 0,
            },
            'liquidity_ratio': 0,
            'capital_adequacy': 0,
        }
        
        return data