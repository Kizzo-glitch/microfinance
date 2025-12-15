from .progress_service import ComplianceProgressService
from .document_service import DocumentStatusService


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
