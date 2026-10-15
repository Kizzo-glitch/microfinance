"""
Document checking — Layer 1: the framework + result model.

HONESTY PRINCIPLE (read before extending):
  We cannot prove a payslip or bank statement is genuine. There's no bank or
  employer API to call. So this NEVER outputs "Verified / Fake". It runs a set
  of consistency and tamper-signal checks, each returning a structured result,
  and aggregates them into a CONFIDENCE BAND + FLAGS. A human lender decides.
  This mirrors the licence model: system surfaces evidence, human verifies.

Each check is a small function: (extracted_data, context) -> CheckResult.
Checks are honest about their own power via `strength`:
  - 'strong'  : math/structural, near-certain when it fails (e.g. balance breaks)
  - 'moderate': suggestive (e.g. PDF producer looks like a design tool)
  - 'weak'    : a hint only (e.g. slightly off font) — informs, doesn't condemn
"""

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"   # couldn't run (missing data, unreadable)


@dataclass
class CheckResult:
    code: str                 # machine id, e.g. 'balance_reconciles'
    label: str                # human label, e.g. 'Running balance reconciles'
    outcome: Outcome
    strength: str             # 'strong' | 'moderate' | 'weak'
    detail: str = ""          # plain-language reason, shown to the lender
    data: dict = field(default_factory=dict)   # supporting figures (optional)

    @property
    def is_flag(self) -> bool:
        """A FAIL is a flag the lender should see. INCONCLUSIVE is not a flag."""
        return self.outcome == Outcome.FAIL


# Confidence bands — derived from results, never asserted as truth.
BAND_HIGH = "high"        # no fails, strong checks passed
BAND_MEDIUM = "medium"    # only weak/moderate fails, or some inconclusive
BAND_LOW = "low"          # a moderate fail, or many inconclusive
BAND_FLAGGED = "flagged"  # any STRONG fail — treat with serious caution
BAND_UNVERIFIABLE = "unverifiable"  # nothing substantive could be checked

BAND_LABELS = {
    BAND_HIGH:    "High confidence — checks passed",
    BAND_MEDIUM:  "Medium confidence — minor flags",
    BAND_LOW:     "Low confidence — review carefully",
    BAND_FLAGGED: "Flagged — strong inconsistency found",
    BAND_UNVERIFIABLE: "Could not verify — document unreadable as expected",
}


def aggregate_band(results):
    """
    Turn a list of CheckResult into one band. Deliberately conservative:
    a single STRONG fail flags the whole document.

    HONESTY RULE: "we checked and it's fine" and "we could NOT check" must never
    look the same. If nothing of substance passed (no strong/moderate PASS) and
    nothing failed, the document is UNVERIFIABLE — not "Medium confidence". A
    random screenshot uploaded as a bank statement lands here: we read nothing,
    so we say so.
    """
    fails = [r for r in results if r.outcome == Outcome.FAIL]
    passes = [r for r in results if r.outcome == Outcome.PASS]
    inconclusive = [r for r in results if r.outcome == Outcome.INCONCLUSIVE]

    if any(r.strength == "strong" for r in fails):
        return BAND_FLAGGED
    if any(r.strength == "moderate" for r in fails):
        return BAND_LOW

    # A 'weak' pass (e.g. "document is readable") is not substance. Require at
    # least one strong/moderate PASS to claim any confidence at all.
    substantive_passes = [r for r in passes if r.strength in ("strong", "moderate")]
    if not substantive_passes:
        return BAND_UNVERIFIABLE

    if fails or len(inconclusive) >= 1:
        return BAND_MEDIUM
    return BAND_HIGH


def run_checks(check_fns, extracted, context):
    """
    Run a list of check functions, swallowing any single check's failure so one
    broken check can't take down the whole assessment (it becomes INCONCLUSIVE).
    Returns (results, band).
    """
    results = []
    for fn in check_fns:
        try:
            r = fn(extracted, context)
            if r is not None:
                results.append(r)
        except Exception as e:  # a check crashing is itself inconclusive, not a pass
            results.append(CheckResult(
                code=getattr(fn, "__name__", "unknown_check"),
                label=getattr(fn, "check_label", "Check"),
                outcome=Outcome.INCONCLUSIVE,
                strength="weak",
                detail=f"Check could not run: {e}",
            ))
    return results, aggregate_band(results)