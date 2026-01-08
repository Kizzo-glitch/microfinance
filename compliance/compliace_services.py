from django.urls import reverse
from .models import ComplianceProfile
from decimal import Decimal


class ComplianceDashboardService:
    def __init__(self, lender):
        self.lender = lender
        self.profile, created = ComplianceProfile.objects.get_or_create(lender=lender)
        
        # FIX: Force a default stage if the database field is empty
        if not self.profile.current_stage:
            self.profile.current_stage = 'document_gathering'
            self.profile.save()

    def get_dashboard_data(self):
        # 1. Check if we even know what they are yet
        if not self.lender.cbl_tier:
            return {
                'is_regulated': True,
                'progress': 0,
                'next_action': "Select CBL Tier in Profile",
                'current_stage': "Tier Assignment",
                'url': reverse('lenders:lender_update', kwargs={'pk': self.lender.pk})
            }
        
        # 2. Non-regulated check
        if not self.lender.requires_cbl_license:
            return {'is_regulated': False, 'progress': 100, 'current_stage': 'Exempt'}

        # 2. Document Requirements based on Tiers
        # Everyone needs these 3
        all_required_docs = ['aml_cft_manual', 'complaints_procedure', 'schedule_i']
        
        # Tier-specific additions
        tier = self.lender.cbl_tier
        if tier == 'tier1':
            all_required_docs += ['business_plan', 'audited_financials', 'risk_management_manual', 
                                 'board_list_with_terms', 'internal_audit_charter', 'memorandum_articles', 'credit_committee_terms']
        elif tier == 'tier2':
            all_required_docs += ['business_plan', 'audited_financials', 'risk_management_manual', 
                                 'board_list_with_terms', 'internal_audit_charter', 'memorandum_articles']
        elif tier == 'tier3':
            all_required_docs += ['financial_statements_certified', 'memorandum_articles']
        elif tier in ['individual', 'p2p']:
            # Individuals/P2P have a light load, but it's NOT zero
            # We already have core docs, maybe add one specific to individual platforms
            pass 

        # 3. Calculate Document Progress
        completed_docs = [f for f in all_required_docs if getattr(self.profile, f)]
        missing_docs = [f for f in all_required_docs if not getattr(self.profile, f)]
        
        # 4. Personnel Requirements
        # Tiers 1-3 are Institutional (need Boards). Individuals/P2P need 1 person.
        if tier in ['individual', 'p2p']:
            required_personnel = 1
        else:
            required_personnel = max(self.lender.minimum_board_size, 3) # Institutions usually need at least 3

        completed_personnel = self.lender.personnel.filter(
            fit_proper_questionnaire_submitted=True
        ).count()

        # 5. Final Calculation
        total_tasks = len(all_required_docs) + required_personnel
        done_tasks = len(completed_docs) + min(completed_personnel, required_personnel)
        
        # Safety: Ensure division by zero doesn't happen and empty lists don't result in 100%
        if total_tasks > 0:
            progress_pct = int((done_tasks / total_tasks) * 100)
        else:
            progress_pct = 0

        # 5. Determine Next Action
        if missing_docs:
            next_action = f"Upload {missing_docs[0].replace('_', ' ').title()}"
            action_url = reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk})
        elif completed_personnel < required_personnel:
            next_action = "Add Personnel & Complete Fit & Proper"
            action_url = reverse('compliance:personnel_create', kwargs={'lender_id': self.lender.pk})
        elif not self.profile.investigation_fee_paid:
            next_action = "Pay Investigation Fee"
            action_url = reverse('compliance:pay_investigation_fee', kwargs={'lender_id': self.lender.pk})
        else:
            next_action = "Submit to CBL"
            action_url = reverse('compliance:submit_application', kwargs={'pk': self.profile.pk})

        return {
            'is_regulated': True,
            'progress': min(progress_pct, 100),
            'current_stage': self.profile.get_current_stage_display() or "Not Started",
            'stage_key': self.profile.current_stage,
            'required_personnel': required_personnel,
            'completed_personnel': completed_personnel,
            'missing_count': len(all_required_docs) - len(completed_docs),

            'next_action': next_action,
            'url': action_url,
        }


class ComplianceDashboardService3:
    def __init__(self, lender):
        self.lender = lender
        # Map ownership_type to a simplified category
        if lender.ownership_type in ['sole_proprietorship', 'peer_to_peer']:
            self.entity_category = 'individual'
        else:
            self.entity_category = 'company'

        self.profile, _ = ComplianceProfile.objects.get_or_create(lender=lender)

        if not self.profile.current_stage:
            self.profile.current_stage = 'document_gathering'
            self.profile.save()

    def get_dashboard_data(self):
        if not self.lender.requires_cbl_license:
            return {'is_regulated': False, 'progress': 100}

        # 1. Document Requirements (Tier-Based)
        # We adjust core docs: Individuals rarely need an 'Institutional' Tax Clearance
        if self.entity_category == 'individual':
            core_docs = ['aml_cft_manual', 'complaints_procedure', 'schedule_i']
        else:
            core_docs = ['aml_cft_manual', 'complaints_procedure', 'tax_clearance_institution', 'schedule_i']
        
        tier_docs = []
        if self.lender.cbl_tier in ['tier1', 'tier2']:
            tier_docs = ['business_plan', 'audited_financials', 'risk_management_manual', 
                         'board_list_with_terms', 'internal_audit_charter', 'memorandum_articles']
            if self.lender.cbl_tier == 'tier1':
                tier_docs.append('credit_committee_terms')
        elif self.lender.cbl_tier == 'tier3':
            tier_docs = ['financial_statements_certified', 'memorandum_articles']

        all_required_docs = core_docs + tier_docs

        # 2. Calculate Document Progress
        completed_docs = [f for f in all_required_docs if getattr(self.profile, f)]
        missing_docs = [f for f in all_required_docs if not getattr(self.profile, f)]

        # 3. Personnel Requirements (Entity-Based)
        # Individuals only require themselves (1). Companies follow minimum board size.
        if self.entity_category == 'individual':
            required_personnel = 1
        else:
            required_personnel = max(self.lender.minimum_board_size, 1)

        completed_personnel = self.lender.personnel.filter(
            fit_proper_questionnaire_submitted=True,
            police_clearance__isnull=False,
            id_copy__isnull=False
        ).count()

        # 4. Final Percentage Logic
        total_tasks = len(all_required_docs) + required_personnel
        done_tasks = len(completed_docs) + min(completed_personnel, required_personnel)
        progress_pct = int((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0

        # 5. Determine Next Action
        if missing_docs:
            next_action = f"Upload {missing_docs[0].replace('_', ' ').title()}"
            action_url = reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk})
        elif completed_personnel < required_personnel:
            next_action = "Add Personnel & Complete Fit & Proper"
            action_url = reverse('compliance:personnel_update', kwargs={'lender_id': self.lender.pk})
        elif not self.profile.investigation_fee_paid:
            next_action = "Pay Investigation Fee"
            action_url = reverse('compliance:pay_investigation_fee', kwargs={'lender_id': self.lender.pk})
        else:
            next_action = "Submit to CBL"
            action_url = reverse('compliance:submit_application', kwargs={'pk': self.profile.pk})

        return {
            'is_regulated': True,
            'progress': min(progress_pct, 100),
            'next_action': next_action,
            'current_stage': self.profile.get_current_stage_display(),
            'stage_key': self.profile.current_stage,
            'url': action_url,
            #'url': reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk}),
            'missing_count': len(missing_docs),
            'required_personnel': required_personnel,
            'completed_personnel': completed_personnel
        }


class ComplianceDashboardService2:
    def __init__(self, lender):
        self.lender = lender
        # Use related_name='compliance' from your model
        self.profile, _ = ComplianceProfile.objects.get_or_create(lender=lender)

    def get_dashboard_data(self):
        # 1. Non-regulated check
        if not self.lender.requires_cbl_license:
            return {'is_regulated': False, 'progress': 100}

        # 2. Define Requirements based on your Model fields
        # Common to all tiers
        core_docs = ['aml_cft_manual', 'complaints_procedure', 'tax_clearance_institution', 'schedule_i']
        
        tier_docs = []
        if self.lender.cbl_tier in ['tier1', 'tier2']:
            tier_docs = ['business_plan', 'audited_financials', 'risk_management_manual', 
                         'board_list_with_terms', 'internal_audit_charter', 'memorandum_articles']
            if self.lender.cbl_tier == 'tier1':
                tier_docs.append('credit_committee_terms')
        elif self.lender.cbl_tier == 'tier3':
            tier_docs = ['financial_statements_certified', 'memorandum_articles']

        all_required_docs = core_docs + tier_docs

        # 3. Calculate Document Progress
        completed_docs = []
        missing_docs = []
        
        for field in all_required_docs:
            file_field = getattr(self.profile, field, None)
            if file_field and hasattr(file_field, 'url'):
                completed_docs.append(field)
            else:
                missing_docs.append(field)

        # 4. Personnel Requirement (Logic from your view)
        required_personnel = max(self.lender.minimum_board_size, 1)

        completed_personnel = self.lender.personnel.filter(
            police_clearance__isnull=False,
            tax_clearance__isnull=False,
            assets_liabilities_statement__isnull=False,
            character_references__isnull=False,
            bank_references__isnull=False,
            id_copy__isnull=False,
            fit_proper_questionnaire_submitted=True,
            schedule_iii_submitted=True
        ).count()

        # 5. Final Percentage Calculation
        # Formula: $Progress = \frac{CompletedDocs + Min(CompletedPers, ReqPers)}{TotalDocs + ReqPers} \times 100$
        total_tasks = len(all_required_docs) + required_personnel
        done_tasks = len(completed_docs) + min(completed_personnel, required_personnel)
        
        progress_pct = int((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0

        # 6. Determine Next Action
        if missing_docs:
            next_action = f"Upload {missing_docs[0].replace('_', ' ').title()}"
        elif completed_personnel < required_personnel:
            next_action = "Complete Personnel Fit & Proper"
        elif not self.profile.investigation_fee_paid:
            next_action = "Pay Investigation Fee"
        else:
            next_action = "Submit to CBL"

        return {
            'is_regulated': True,
            'progress': min(progress_pct, 100),
            'next_action': next_action,
            'current_stage': self.profile.get_current_stage_display(),
            'stage_key': self.profile.current_stage,
            'url': reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk}),
            'missing_count': len(missing_docs)
        }
