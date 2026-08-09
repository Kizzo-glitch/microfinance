"""
Fedha-Grow — expense reconciliation
===================================
Compares a borrower's DECLARED monthly expenses against OUTFLOWS observed on an
uploaded bank statement, and cross-checks names across profile / statement / ID.

Output is a set of REVIEW SIGNALS for the lender, never an automated verdict:
  - a large "declared far below observed" gap suggests under-declaration
  - a name mismatch suggests the statement may not be the borrower's
Both are flags for a human, calibrated so that "couldn't verify" is never
reported as "borrower lied".
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal

from .parser import ParsedStatement
from .matching import match_names, NameMatchResult, NameMatchBand


# How far below observed outflows a declaration can sit before we flag it.
# 0.60 => if declared is less than 60% of observed spending, raise a flag.
DECLARED_VS_OBSERVED_FLOOR = Decimal("0.60")


@dataclass
class ReconciliationResult:
    # expense reconciliation
    declared_expenses: Decimal
    observed_outflows: Decimal
    coverage_ratio: Decimal            # declared / observed (0 if observed 0)
    expense_flag: bool = False
    expense_note: str = ""

    # name cross-checks (soft signals)
    statement_name_match: NameMatchResult = None
    id_name_match: NameMatchResult = None

    # overall
    parse_confidence: str = "low"
    signals: list = field(default_factory=list)   # human-readable review notes

    @property
    def needs_review(self) -> bool:
        return self.expense_flag or any(
            m and m.is_flag for m in (self.statement_name_match, self.id_name_match)
        )


def reconcile(
    *,
    declared_expenses: Decimal,
    statement: ParsedStatement,
    profile_name: str = "",
    id_name: str = "",
) -> ReconciliationResult:
    declared = Decimal(declared_expenses or 0)
    observed = statement.total_outflows or Decimal("0.00")

    coverage = (declared / observed) if observed > 0 else Decimal("0.00")

    signals: list[str] = []
    expense_flag = False
    expense_note = ""

    # Only reconcile if we actually parsed spending; otherwise it's "unverified",
    # NOT "under-declared".
    if not statement.is_parseable or observed <= 0:
        expense_note = (
            "Could not read enough transactions to check declared expenses. "
            "Treat expenses as unverified rather than confirmed."
        )
        signals.append(expense_note)
    else:
        if coverage < DECLARED_VS_OBSERVED_FLOOR:
            expense_flag = True
            expense_note = (
                f"Declared expenses (M{declared:,.2f}) are well below the "
                f"spending seen on the statement (M{observed:,.2f}). "
                f"Possible under-declaration — recommend lender review."
            )
            signals.append(expense_note)
        else:
            expense_note = (
                f"Declared expenses broadly consistent with observed outflows "
                f"(coverage {coverage:.0%})."
            )

    # ---- name cross-checks (soft) ----
    stmt_match = None
    if profile_name and statement.account_holder:
        stmt_match = match_names(profile_name, statement.account_holder)
        if stmt_match.is_flag:
            signals.append(
                f"Statement name '{statement.account_holder}' does not match "
                f"profile name '{profile_name}' — verify ownership of the account."
            )
        elif stmt_match.band == NameMatchBand.NOT_FOUND:
            signals.append("Could not read a name on the statement to cross-check.")

    id_match = None
    if profile_name and id_name:
        id_match = match_names(profile_name, id_name)
        if id_match.is_flag:
            signals.append(
                f"ID name '{id_name}' does not match profile name "
                f"'{profile_name}' — verify identity documents."
            )

    return ReconciliationResult(
        declared_expenses=declared.quantize(Decimal("0.01")),
        observed_outflows=observed.quantize(Decimal("0.01")),
        coverage_ratio=coverage.quantize(Decimal("0.01")),
        expense_flag=expense_flag,
        expense_note=expense_note,
        statement_name_match=stmt_match,
        id_name_match=id_match,
        parse_confidence=statement.parse_confidence,
        signals=signals,
    )