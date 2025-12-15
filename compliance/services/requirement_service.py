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
