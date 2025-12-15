from datetime import timezone
from compliance.models import ComplianceDocument

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



# compliance/services/document_status.py
"""
from compliance.models import LenderComplianceRecord


class DocumentStatusService:
    def __init__(self, record: LenderComplianceRecord):
        self.record = record

    def missing_company_docs(self):
        ci = self.record.company_info
        if not ci:
            return ["Company Information not started"]

        missing = []
        if not ci.registration_cert:
            missing.append("Registration Certificate")
        if not ci.tax_clearance:
            missing.append("Tax Clearance")
        if not ci.proof_of_capital:
            missing.append("Proof of Capital")

        return missing

    def missing_director_docs(self):
        missing = []
        for d in self.record.directors.all():
            if not d.is_complete():
                missing.append(d.full_name)
        return missing

    def missing_submission_docs(self):
        sub = self.record.submission
        if not sub:
            return ["Submission section not started"]

        missing = []
        if not sub.schedule1_form:
            missing.append("Schedule I")
        if not sub.schedule2_form:
            missing.append("Schedule II")
        if not sub.investigation_fee_receipt:
            missing.append("Investigation Fee Receipt")

        return missing
"""