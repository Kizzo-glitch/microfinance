from decimal import Decimal
from lenders.models import LenderProfile


class TierAssessmentService:
    """
    Determines appropriate CBL tier and validates tier requirements
    """

    @staticmethod
    def recommend_tier(lender: LenderProfile) -> str:
        if lender.total_assets and lender.total_assets >= Decimal('10000000'):
            return 'tier2'
        if lender.stated_capital and lender.stated_capital >= Decimal('500000'):
            return 'tier3'
        return 'individual'

    @staticmethod
    def meets_minimum_capital(lender: LenderProfile, tier: str) -> bool:
        min_required = lender.minimum_capital_requirement
        return lender.stated_capital and lender.stated_capital >= min_required

    @staticmethod
    def minimum_board_required(tier: str) -> int:
        return {
            'tier1': 5,
            'tier2': 5,
            'tier3': 3,
            'individual': 0,
            'p2p': 0,
        }.get(tier, 0)
