from .requirement_service import RequirementEvaluatorService


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
