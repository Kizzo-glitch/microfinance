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

