"""
Fedha-Grow — name matching
===========================
Fuzzy, order-insensitive name comparison for cross-verifying a borrower's
profile name against names read (by OCR) from a bank statement and/or ID copy.

DESIGN: this produces a SOFT signal, never a gate.
  - Names are noisy: banks reorder ("SURNAME FIRSTNAME"), abbreviate ("B."),
    drop middle names, add titles. OCR mangles them further on scans/photos.
  - So we return a similarity band, and "couldn't read a name" is distinct
    from "the name doesn't match". Only a confident, strong mismatch is a flag,
    and even then it's for lender review — never an automated rejection.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
from rapidfuzz import fuzz


class NameMatchBand(str, Enum):
    STRONG     = "strong"       # very likely the same person
    PARTIAL    = "partial"      # overlaps, but not conclusive
    WEAK       = "weak"         # little overlap
    NONE       = "none"         # effectively no overlap -> review flag
    NOT_FOUND  = "not_found"    # no name could be extracted (OCR/parse failure)


# Titles/honorifics and noise tokens we strip before comparing.
_NOISE = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "rev", "sir", "madam",
    "the", "and",
}


def _normalise(name: str) -> list[str]:
    """Lowercase, strip punctuation/titles, return a sorted token list."""
    if not name:
        return []
    name = name.lower()
    name = re.sub(r"[^a-z\s]", " ", name)          # drop digits/punctuation
    tokens = [t for t in name.split() if t and t not in _NOISE]
    # collapse single-letter initials to just the letter (keeps "b" from "b.")
    return sorted(tokens)


@dataclass
class NameMatchResult:
    band: NameMatchBand
    score: float                 # 0-100 similarity (0 when not found)
    profile_name: str
    observed_name: str
    note: str = ""

    @property
    def is_flag(self) -> bool:
        """Only a confident NONE is worth flagging for review."""
        return self.band == NameMatchBand.NONE

    @property
    def corroborates(self) -> bool:
        """STRONG match gently raises confidence elsewhere."""
        return self.band == NameMatchBand.STRONG


def match_names(profile_name: str, observed_name: str) -> NameMatchResult:
    p_tokens = _normalise(profile_name)
    o_tokens = _normalise(observed_name)

    if not o_tokens:
        return NameMatchResult(
            band=NameMatchBand.NOT_FOUND, score=0.0,
            profile_name=profile_name, observed_name=observed_name,
            note="No readable name to compare (likely OCR/scan limitation).",
        )
    if not p_tokens:
        return NameMatchResult(
            band=NameMatchBand.NOT_FOUND, score=0.0,
            profile_name=profile_name, observed_name=observed_name,
            note="No profile name on record to compare against.",
        )

    # token_sort_ratio is order-insensitive: "bokang ntsonyane" == "ntsonyane bokang"
    p = " ".join(p_tokens)
    o = " ".join(o_tokens)
    score = float(fuzz.token_sort_ratio(p, o))

    # Bonus: reward shared full tokens (surname match matters more than fuzz).
    shared = set(p_tokens) & set(o_tokens)
    if shared:
        coverage = len(shared) / min(len(p_tokens), len(o_tokens))
        score = max(score, coverage * 100.0)

    band = (
        NameMatchBand.STRONG  if score >= 85 else
        NameMatchBand.PARTIAL if score >= 60 else
        NameMatchBand.WEAK    if score >= 35 else
        NameMatchBand.NONE
    )

    notes = {
        NameMatchBand.STRONG:  "Names align strongly.",
        NameMatchBand.PARTIAL: "Names partially overlap — corroborating but not conclusive.",
        NameMatchBand.WEAK:    "Names overlap weakly — treat with caution.",
        NameMatchBand.NONE:    "Names do not appear to match — flag for lender review.",
    }
    return NameMatchResult(
        band=band, score=round(score, 1),
        profile_name=profile_name, observed_name=observed_name,
        note=notes[band],
    )