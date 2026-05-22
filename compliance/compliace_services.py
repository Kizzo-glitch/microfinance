from django.urls import reverse
from .models import ComplianceProfile
from decimal import Decimal
from django.utils import timezone



class ComplianceDashboardService:
    """
    Computes the compliance dashboard state for a single lender.

    Responsibilities:
      - Determine which documents are required for this lender's tier
      - Count verified personnel against CBL minimums
      - Calculate progress percentage
      - Determine the correct current stage (read-only — no mutation on load)
      - Produce the next action prompt and URL

    Does NOT mutate stage on every read. Stage is only written when
    explicitly advanced via `advance_stage()`.
    """

    # Fix 6: Human-readable labels for all required document fields
    DOCUMENT_LABELS = {
        'schedule_i':                     'Schedule I — Application Form',
        'schedule_ii':                    'Schedule II — Information Sheet',
        'tax_clearance_institution':      'Company Tax Clearance Certificate',
        'business_plan':                  'Detailed Business Plan',
        'audited_financials':             'Audited Financial Statements (2 years)',
        'financial_statements_certified': 'Financial Statements (Certified Accountant)',
        'capital_commitment_letter':      'Capital Commitment Letter',
        'bank_statements_capital':        'Bank Statements (Capital Evidence)',
        'risk_management_manual':         'Risk Management Manual',
        'aml_cft_manual':                 'AML/CFT Policy Manual',
        'complaints_procedure':           'Consumer Complaints & Redress Procedure',
        'memorandum_articles':            'Memorandum & Articles of Association',
        'home_supervisor_consent':        'Home Country Supervisor Consent',
        'board_resolution_for_licensing': 'Board Resolution for Licensing',
        'board_list_with_terms':          'Board of Directors List with Terms',
        'credit_committee_terms':         'Board Credit Committee Terms',
        'internal_audit_charter':         'Internal Audit Charter',
    }

    # Tier-specific required document fields, matched to actual model field names
    BASE_DOCS = [
        'schedule_i',
        'schedule_ii',
        'tax_clearance_institution',
        'bank_statements_capital',
        'capital_commitment_letter',
        'aml_cft_manual',
        'complaints_procedure',
        'memorandum_articles',
    ]

    TIER1_TIER2_DOCS = BASE_DOCS + [
        'business_plan',
        'audited_financials',
        'risk_management_manual',
        'board_list_with_terms',
        'internal_audit_charter',
        'board_resolution_for_licensing',
    ]

    TIER1_ONLY_DOCS = TIER1_TIER2_DOCS + [
        'credit_committee_terms',
    ]

    TIER3_DOCS = BASE_DOCS + [
        'financial_statements_certified',
    ]

    # Minimum fully-verified personnel per tier
    PERSONNEL_MINIMUMS = {
        'tier1': 5,
        'tier2': 5,
        'tier3': 1,
    }

    def __init__(self, lender):
        self.lender = lender
        # Fix 2: Don't default stage here. get_or_create is enough.
        # The model's default='not_started' handles new profiles correctly.
        self.profile, _ = ComplianceProfile.objects.get_or_create(lender=lender)

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    def get_dashboard_data(self):
        """
        Returns a dict of display-ready data for the compliance dashboard.
        This method is READ-ONLY — it never writes to the database.
        """
        if not self.lender.cbl_tier:
            return self._no_tier_response()

        required_docs = self._get_required_docs()
        missing_docs = self._get_missing_docs(required_docs)
        completed_docs = required_docs - missing_docs

        personnel_data = self._get_personnel_data()
        fee_data = self._get_fee_data()

        progress = self._calculate_progress(
            completed_docs, required_docs, personnel_data, fee_data
        )

        # Fix 1 + Fix 5: Derive stage from data state; never write it here
        derived_stage = self._derive_stage(missing_docs, personnel_data, fee_data)
        next_action = self._get_next_action(missing_docs, personnel_data, fee_data)

        return {
            'is_regulated': True,
            'progress': progress,
            'current_stage': self._stage_display(derived_stage),
            'stage_key': derived_stage,

            # Documents
            'total_docs_required': len(required_docs),
            'completed_docs_count': len(completed_docs),
            'missing_docs': [
                self.DOCUMENT_LABELS.get(f, f) for f in missing_docs
            ],

            # Personnel
            'required_personnel': personnel_data['required'],
            'completed_personnel': personnel_data['verified_count'],
            'personnel_missing': personnel_data['required'] - personnel_data['verified_count'],

            # Fees
            'investigation_fee_paid': fee_data['investigation'],
            'registration_fee_paid': fee_data['registration'],
            'license_fee_paid': fee_data['license'],

            # Next action
            'next_action': next_action['label'],
            'url': next_action['url'],
            'status_message': next_action['message'],
        }

    def advance_stage(self, new_stage):
        """
        The ONLY method that writes stage to the database.
        Call this explicitly from a view after a user action
        (e.g. submitting the application, paying a fee).

        Fix 5: Stage mutation is intentional and explicit, not a side-effect of reading.
        Fix 1: Validates the stage key before writing.
        """
        valid_stages = {key for key, _ in ComplianceProfile.STAGE_CHOICES}
        if new_stage not in valid_stages:
            raise ValueError(
                f"'{new_stage}' is not a valid stage. "
                f"Valid choices: {valid_stages}"
            )
        if self.profile.current_stage != new_stage:
            self.profile.current_stage = new_stage
            self.profile.save(update_fields=['current_stage'])

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _get_required_docs(self):
        """
        Returns the set of field names required for this lender's tier.
        Fix 4: Now includes all CBL-required fields (board resolution,
        credit committee terms, capital commitment, etc.)
        """
        tier = self.lender.cbl_tier
        if tier == 'tier1':
            docs = set(self.TIER1_ONLY_DOCS)
        elif tier == 'tier2':
            docs = set(self.TIER1_TIER2_DOCS)
        elif tier == 'tier3':
            docs = set(self.TIER3_DOCS)
        else:
            docs = set(self.BASE_DOCS)

        # Foreign institutions always need home supervisor consent
        if getattr(self.lender, 'is_foreign_entity', False):
            docs.add('home_supervisor_consent')

        return docs

    def _get_missing_docs(self, required_docs):
        """Returns the subset of required_docs that have no file uploaded."""
        return {
            field for field in required_docs
            if not getattr(self.profile, field, None)
        }

    def _get_personnel_data(self):
        """Counts verified personnel against the tier minimum."""
        required = self.PERSONNEL_MINIMUMS.get(self.lender.cbl_tier, 1)
        all_personnel = self.lender.personnel.all()

        verified_count = sum(
            1 for person in all_personnel
            if person.is_fully_verified()
        )

        return {
            'required': required,
            'verified_count': verified_count,
            'is_met': verified_count >= required,
        }

    def _get_fee_data(self):
        """Collects current fee payment state from ComplianceProfile."""
        return {
            'investigation': self.profile.investigation_fee_paid,
            'registration': self.profile.registration_fee_paid,
            'license': self.profile.license_fee_paid,
            'renewal': self.profile.renewal_fee_paid,
        }

    def _calculate_progress2(self, completed_docs, required_docs, personnel_data, fee_data):
        """
        Fix 4: Progress now includes all task categories:
          - Documents (weighted by count)
          - Personnel verification
          - Investigation fee
        Post-submission fees (registration, license) are not in the
        pre-submission progress bar — they belong to a separate post-approval flow.
        """
        doc_total = len(required_docs)
        doc_done = len(completed_docs)

        person_total = personnel_data['required']
        person_done  = min(personnel_data['verified_count'], person_total)

        fee_total = 1  # Just the investigation fee pre-submission
        fee_done = 1 if fee_data['investigation'] else 0

        total_tasks = doc_total + person_total + fee_total
        done_tasks = doc_done + person_done + fee_done

        if total_tasks == 0:
            return 0

        return min(int((done_tasks / total_tasks) * 100), 100)

    def _calculate_progress(self, completed_docs, required_docs, personnel_data, fee_data):
        doc_total    = len(required_docs)
        doc_done     = len(completed_docs)
        person_total = personnel_data['required']
        person_done  = min(personnel_data['verified_count'], person_total)
        fee_total    = 1
        fee_done     = 1 if fee_data['investigation'] else 0
        
        total_tasks  = doc_total + person_total + fee_total
        done_tasks   = doc_done  + person_done  + fee_done
        
        print(f"Progress calc: {done_tasks}/{total_tasks} = {(done_tasks/total_tasks)*100}%")  # Debug
        
        return min(int((done_tasks / total_tasks) * 100), 100) if total_tasks > 0 else 0


    def _derive_stage(self, missing_docs, personnel_data, fee_data):
        """
        Fix 1 + Fix 5: Derives the logical current stage from data state.
        Uses only valid STAGE_CHOICES keys.
        Returns the stage key string — does not write to DB.
        """
        current = self.profile.current_stage

        # Post-submission stages are set by admin, not derived here.
        # Respect them and don't override.
        post_submission_stages = {
            'submitted', 'under_review',
            'registration_fee_pending', 'license_fee_pending',
            'licensed', 'renewal_fee_pending', 'renewal_under_review',
            'rejected', 'suspended', 'revoked',
        }
        if current in post_submission_stages:
            return current

        # Pre-submission: derive from state
        if missing_docs:
            return 'document_gathering'

        if not personnel_data['is_met']:
            return 'fit_proper_pending'      # Fix 1: correct key from STAGE_CHOICES

        if not fee_data['investigation']:
            return 'investigation_fee_pending'  # Fix 1: correct key from STAGE_CHOICES

        # All pre-submission requirements met — ready to submit
        return 'not_started' if current == 'not_started' else current

    def _get_next_action(self, missing_docs, personnel_data, fee_data):
        """
        Fix 6: Uses DOCUMENT_LABELS for human-readable text.
        Returns a dict with label, url, and message.
        """
        lender_id = self.lender.pk
        current = self.profile.current_stage

        # Post-submission — no action for the lender to take
        if current in ('submitted', 'under_review'):
            return {
                'label': None,
                'url': None,
                'message': 'Your application is under CBL review. We will notify you of any updates.',
            }

        if current == 'registration_fee_pending':
            return {
                'label': 'Pay Registration Fee',
                'url': reverse('compliance:pay_registration_fee', kwargs={'lender_id': lender_id}),
                'message': 'CBL has approved your application. Please pay the registration fee.',
            }

        if current == 'license_fee_pending':
            return {
                'label': 'Pay Licence Fee',
                'url': reverse('compliance:pay_license_fee', kwargs={'lender_id': lender_id}),
                'message': 'Registration confirmed. Please pay the licence fee to receive your licence.',
            }

        if current == 'renewal_fee_pending':
            return {
                'label': 'Pay Annual Renewal Fee',
                'url': reverse('compliance:pay_renewal_fee', kwargs={'lender_id': lender_id}),
                'message': 'Your licence is due for renewal. Please pay the annual renewal fee.',
            }

        if current == 'licensed':
            return {
                'label': None,
                'url': None,
                'message': 'Your institution is fully licensed by the Central Bank of Lesotho.',
            }

        # Pre-submission: check in priority order
        if missing_docs:
            # Fix 6: Use human-readable label, not raw field name
            first_missing_label = self.DOCUMENT_LABELS.get(
                next(iter(missing_docs)), 'Required Document'
            )
            return {
                'label': f'Upload: {first_missing_label}',
                'url': reverse('compliance:compliance_detail', kwargs={'lender_id': lender_id}),
                'message': f'{len(missing_docs)} document(s) still required.',
            }

        if not personnel_data['is_met']:
            remaining = personnel_data['required'] - personnel_data['verified_count']
            return {
                'label': f'Complete Personnel Files ({remaining} remaining)',
                'url': reverse('compliance:personnel_list', kwargs={'lender_id': lender_id}),
                'message': f"CBL requires {personnel_data['required']} fully verified personnel.",
            }

        if not fee_data['investigation']:
            return {
                'label': 'Pay Investigation Fee',
                'url': reverse('compliance:pay_investigation_fee', kwargs={'lender_id': lender_id}),
                'message': 'All documents verified. Pay the investigation fee to proceed.',
            }

        # All pre-submission gates passed
        return {
            'label': 'Submit Application to CBL',
            'url': reverse('compliance:submit_application', kwargs={'lender_id': lender_id}),
            'message': 'All requirements met. Your application is ready for submission.',
        }

    def _stage_display(self, stage_key):
        """Returns the human-readable label for a stage key."""
        stage_map = dict(ComplianceProfile.STAGE_CHOICES)
        return stage_map.get(stage_key, stage_key)

    def _no_tier_response(self):
        return {
            'is_regulated': True,
            'progress': 0,
            'current_stage': 'Tier Not Set',
            'stage_key': 'not_started',
            'next_action': 'Select Your CBL Tier',
            'url': reverse('lenders:lender_profile', kwargs={'pk': self.lender.pk}),
            'status_message': 'Please complete your profile and select a CBL tier to begin.',
            'missing_docs': [],
            'completed_docs_count': 0,
            'total_docs_required':  0,
            'required_personnel': 0,
            'completed_personnel': 0,
            'personnel_missing': 0,
            'investigation_fee_paid': False,
            'registration_fee_paid': False,
            'license_fee_paid': False,
        }







class ComplianceDashboardService2:
    def __init__(self, lender):
        self.lender = lender
        self.profile, created = ComplianceProfile.objects.get_or_create(lender=lender)
        
        if not self.profile.current_stage:
            self.profile.current_stage = 'document_gathering'
            self.profile.save()

    def get_dashboard_data(self):
        if not self.lender.cbl_tier:
            return {
                'is_regulated': True, 'progress': 0, 'next_action': "Select CBL Tier",
                'current_stage': "Tier Assignment",
                'url': reverse('lenders:lender_profile', kwargs={'pk': self.lender.pk})
            }
        
        tier = self.lender.cbl_tier
        
        # 1. Document Requirements (CBL Checklist)
        all_required_docs = [
            'aml_cft_manual', 'complaints_procedure', 'schedule_i', 
            'schedule_ii', 'tax_clearance_institution', 'bank_statements_capital'         
        ]
        
        if tier in ['tier1', 'tier2']:
            all_required_docs += ['business_plan', 'audited_financials', 'risk_management_manual', 
                                 'board_list_with_terms', 'internal_audit_charter', 'memorandum_articles']
        elif tier == 'tier3':
            all_required_docs += ['financial_statements_certified', 'memorandum_articles']

        completed_docs = [f for f in all_required_docs if getattr(self.profile, f)]
        missing_docs = [f for f in all_required_docs if not getattr(self.profile, f)]

        # 2. Personnel Count (CBL: 5 for Tiers 1/2)
        required_personnel = 5 if tier in ['tier1', 'tier2'] else 3
        personnel_qs = self.lender.personnel.all()
        
        # Logic Fix: Count only those who passed the 10-doc check
        verified_personnel_count = 0
        for person in personnel_qs:
            if hasattr(person, 'is_fully_verified') and person.is_fully_verified():
                verified_personnel_count += 1

        # 3. Progress Calculation (FIXED: Moved logic order)
        total_tasks = len(all_required_docs) + required_personnel + 1
        done_tasks = len(completed_docs) + verified_personnel_count
        if self.profile.investigation_fee_paid: 
            done_tasks += 1
        
        if self.profile.current_stage == 'under_review':
            progress_pct = 100
            next_action = None
            action_url = None
            status_message = "Your application is currently being processed."
        else:
            progress_pct = int((done_tasks / total_tasks) * 100) if total_tasks > 0 else 0

            # 4. State Management
            if missing_docs:
                self._update_stage('document_gathering')
                next_action = f"Upload {missing_docs[0].replace('_', ' ').title()}"
                action_url = reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk})
                status_message = "Institutional documentation is incomplete."

            elif verified_personnel_count < required_personnel:
                # FIXED: Stage key should match model choices (usually 'fit_proper')
                self._update_stage('fit_proper_pending')
                remainder = required_personnel - verified_personnel_count
                next_action = f"Complete Personnel Files ({remainder} left)"
                # FIXED: Point to list so they can see what's missing
                action_url = reverse('compliance:personnel_list', kwargs={'lender_id': self.lender.pk})
                status_message = f"CBL requires {required_personnel} fully verified members."

            elif not self.profile.investigation_fee_paid:
                self._update_stage('payment_pending')
                next_action = "Pay Investigation Fee"
                action_url = reverse('compliance:pay_investigation_fee', kwargs={'lender_id': self.lender.pk})
                status_message = "All documents verified. Please proceed to payment."

            else:
                next_action = "Submit to CBL"
                action_url = reverse('compliance:submit_application', kwargs={'lender_id': self.lender.pk})
                status_message = "All requirements met. Ready for submission."

        return {
            'is_regulated': True,
            'progress': min(progress_pct, 100),
            'current_stage': self.profile.get_current_stage_display(),
            'stage_key': self.profile.current_stage,
            'required_personnel': required_personnel,
            # FIXED: Sending integer count for the badge
            'completed_personnel': verified_personnel_count, 
            'missing_count': len(missing_docs),
            'next_action': next_action,
            'url': action_url,
            'status_message': status_message,
        }

    def _update_stage(self, new_stage):
        if self.profile.current_stage != new_stage:
            self.profile.current_stage = new_stage
            self.profile.save()




class ComplianceDashboardService3:
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
                'url': reverse('lenders:lender_profile', kwargs={'pk': self.lender.pk})
            }
        
        # 2. Non-regulated check
        if not self.lender.requires_cbl_license:
            return {'is_regulated': False, 'progress': 100, 'current_stage': 'Exempt'}

        # 2. Document Requirements based on Tiers
        # Everyone needs these 3
        #all_required_docs = ['aml_cft_manual', 'complaints_procedure', 'schedule_i']
        all_required_docs = [
            'aml_cft_manual', 
            'complaints_procedure', 
            'schedule_i', 
            'schedule_ii', 
            'tax_clearance_institution',   
            'bank_statements_capital'         
        ]
        
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

        elif tier in ['tier1', 'tier2']:
            required_personnel = 5

        else:
            required_personnel = max(self.lender.minimum_board_size, 3) # Institutions usually need at least 3

        completed_personnel2 = self.lender.personnel.filter(
            fit_proper_questionnaire_submitted=True
        ).count()

        personnel_qs = self.lender.personnel.all()
        verified_personnel_count = 0

        for person in personnel_qs:
            if hasattr(person, 'is_fully_verified') and person.is_fully_verified():
                verified_personnel_count += 1

        # Return stats (Use the updated math from previous turn)
        total_tasks = len(all_required_docs) + required_personnel + 1 # +1 for payment
        done_tasks = len(completed_docs) + verified_personnel_count

        if self.profile.investigation_fee_paid: done_tasks += 1
        
        progress_pct = 100 if self.profile.current_stage == 'under_review' else int((done_tasks / total_tasks) * 100)
        
        # Safety: Ensure division by zero doesn't happen and empty lists don't result in 100%
        if total_tasks > 0:
            progress_pct = int((done_tasks / total_tasks) * 100)
        else:
            progress_pct = 0


        # Determine the status based on progress
        if self.profile.current_stage == 'under_review':
            next_action = None
            action_url = None
            status_message = "Your application is currently being processed."
        
        elif missing_docs:
            # SYNC STAGE: If docs are missing, we are in gathering
            if self.profile.current_stage != 'document_gathering':
                self.profile.current_stage = 'document_gathering'
                self.profile.save()
            next_action = f"Upload {missing_docs[0].replace('_', ' ').title()}"
            action_url = reverse('compliance:compliance_detail', kwargs={'lender_id': self.lender.pk})
            status_message = "Institutional documentation is incomplete."

        elif verified_personnel_count < required_personnel: #completed_personnel < required_personnel:
            # SYNC STAGE: If docs done but personnel missing
            if self.profile.current_stage != 'Adding Personnel':
                self.profile.current_stage = 'Adding Personnel'
                self.profile.save()
            remainder = required_personnel - verified_personnel_count #required_personnel - completed_personnel
            next_action = f"Add Personnel (Need {remainder} more)"
            action_url = reverse('compliance:personnel_create', kwargs={'lender_id': self.lender.pk})
            status_message = f"Personnel requirement: {required_personnel} members."

        elif not self.profile.investigation_fee_paid:
            # SYNC STAGE: If docs/personnel done but no payment
            if self.profile.current_stage != 'payment_pending':
                self.profile.current_stage = 'payment_pending'
                self.profile.save()
            next_action = "Pay Investigation Fee"
            action_url = reverse('compliance:pay_investigation_fee', kwargs={'lender_id': self.lender.pk})
            status_message = "Please upload proof of payment to proceed."

        else:
            # SYNC STAGE: Everything done
            next_action = "Submit to CBL"
            action_url = reverse('compliance:submit_application', kwargs={'lender_id': self.lender.pk})
            status_message = "All requirements met. Ready for submission."

        return {
            'is_regulated': True,
            'progress': min(progress_pct, 100),
            'current_stage': self.profile.get_current_stage_display() or "Not Started",
            'stage_key': self.profile.current_stage,
            'required_personnel': required_personnel,
            'completed_personnel': personnel_qs,
            'missing_count': len(all_required_docs) - len(completed_docs),

            'next_action': next_action,
            'url': action_url,
            'status_message': status_message,
        }


