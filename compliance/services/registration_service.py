from compliance.models import CBLRegistration
from .tier_service import TierAssessmentService


class RegistrationService:

    @staticmethod
    def get_or_create_registration(lender_profile):
        registration, created = CBLRegistration.objects.get_or_create(
            lender_profile=lender_profile
        )

        if created:
            tier = lender_profile.cbl_tier or TierAssessmentService.recommend_tier(lender_profile)
            registration.target_tier = tier
            registration.set_tier_requirements()
            registration.save()

        return registration
