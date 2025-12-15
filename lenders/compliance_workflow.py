from django.utils import timezone

class ComplianceWorkflowService:

    def __init__(self, registration):
        self.registration = registration

    # ---------------------------------------------------------
    # Progression Logic
    # ---------------------------------------------------------
    def advance_stage(self):
        stages = [s[0] for s in self.registration.STAGES]
        current_index = stages.index(self.registration.current_stage)

        if current_index < len(stages) - 1:
            self.registration.current_stage = stages[current_index + 1]
            self.registration.save()

    def regress_stage(self):
        stages = [s[0] for s in self.registration.STAGES]
        current_index = stages.index(self.registration.current_stage)

        if current_index > 0:
            self.registration.current_stage = stages[current_index - 1]
            self.registration.save()