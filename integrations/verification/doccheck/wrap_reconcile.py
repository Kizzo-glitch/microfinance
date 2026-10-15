"""
Document checking — Layer 2 (CORRECTED to your real ReconciliationResult).

Your reconcile() does NOT do running-balance reconciliation — your parser
doesn't extract a per-row balance column. What it DOES do:
  - expense coverage: declared_expenses vs observed outflows (catches
    under-declaration), via `expense_flag` / `expense_note` / `coverage_ratio`
  - name matching: `statement_name_match` / `id_name_match`
    (NameMatchResult with `.is_flag`, `.band`)
  - `parse_confidence`, and a ready-made `signals` list of review notes
  - a `needs_review` aggregate property

So these checks TRANSLATE those real fields into CheckResult flags. No field is
invented; nothing recomputes what reconcile() already decided.

IMPORTANT honesty note: because there's no balance column, we DON'T claim
"running balance reconciles" (we can't). The strongest signal here is expense
coverage + name match. That's what the lender sees, truthfully labelled.
"""

from decimal import Decimal
from .framework import CheckResult, Outcome, run_checks


# ---------------------------------------------------------------------------
# Checks read context['ocr'] (the OCRAnalysis) -> .reconciliation / .statement.
# ---------------------------------------------------------------------------

def check_expense_coverage(extracted, context):
    """
    STRONG-ish. Does declared spending line up with what the statement shows?
    reconcile() sets expense_flag=True when declared is well below observed
    (possible under-declaration). When it couldn't parse enough, it's
    inconclusive (reconcile() treats this as 'unverified', not 'under-declared').
    """
    recon = _recon(context)
    if recon is None:
        return CheckResult(
            "expense_coverage", "Declared expenses match the statement",
            Outcome.INCONCLUSIVE, "strong",
            "No reconciliation result (statement could not be read).")

    # reconcile() already decided whether this is checkable: coverage_ratio 0
    # with an expense_note about being unverified means it couldn't check.
    coverage = getattr(recon, "coverage_ratio", Decimal("0"))
    flagged = getattr(recon, "expense_flag", False)
    note = getattr(recon, "expense_note", "")

    if coverage == 0 and not flagged:
        # reconcile()'s "couldn't read enough / unverified" branch.
        return CheckResult(
            "expense_coverage", "Declared expenses match the statement",
            Outcome.INCONCLUSIVE, "strong",
            note or "Not enough spending was read to check declared expenses.")

    if flagged:
        return CheckResult(
            "expense_coverage", "Declared expenses match the statement",
            Outcome.FAIL, "strong",
            detail=note or "Declared expenses are well below the spending seen "
                           "on the statement — possible under-declaration.")

    return CheckResult(
        "expense_coverage", "Declared expenses match the statement",
        Outcome.PASS, "strong",
        note or f"Declared expenses are consistent with observed spending "
                f"(coverage {coverage:.0%}).")


def check_statement_name(extracted, context):
    """MODERATE. Does the name on the STATEMENT match the profile?"""
    recon = _recon(context)
    if recon is None:
        return None
    return _name_check(
        getattr(recon, "statement_name_match", None),
        code="statement_name",
        label="Statement name matches profile",
        pass_detail="The account holder name matches the borrower's profile.",
        fail_detail="The statement's account holder name doesn't match the "
                    "borrower's profile — verify who owns the account.",
        missing_detail="No name could be read on the statement to cross-check.",
    )


def check_id_name(extracted, context):
    """MODERATE. Does the name on the ID match the profile?"""
    recon = _recon(context)
    if recon is None:
        return None
    return _name_check(
        getattr(recon, "id_name_match", None),
        code="id_name",
        label="ID name matches profile",
        pass_detail="The ID name matches the borrower's profile.",
        fail_detail="The ID name doesn't match the borrower's profile — "
                    "verify identity documents.",
        missing_detail="No ID name was available to cross-check.",
    )


def check_parse_confidence(extracted, context):
    """
    WEAK. Low parse confidence isn't fraud — it means the other checks are less
    reliable. Surfaced as context (inconclusive), never a borrower 'fail'.
    """
    recon = _recon(context)
    conf = getattr(recon, "parse_confidence", None) if recon else None
    if conf is None:
        ocr = context.get("ocr")
        conf = getattr(ocr, "ocr_confidence", "low") if ocr else "low"
    if conf == "low":
        return CheckResult(
            "parse_confidence", "Document is clearly readable",
            Outcome.INCONCLUSIVE, "weak",
            "The document read poorly, so automated checks are less reliable. "
            "A clearer copy would allow a firmer assessment.")
    return CheckResult(
        "parse_confidence", "Document is clearly readable",
        Outcome.PASS, "weak", f"Document parsed at {conf} confidence.")


STATEMENT_CHECKS_FROM_RECON = [
    check_expense_coverage,
    check_statement_name,
    check_id_name,
    check_parse_confidence,
]


def assess_statement(ocr_analysis, extra_checks=None):
    """
    ocr_analysis : OCRAnalysis from TesseractDocumentAdapter.analyse_statement()
    extra_checks : optional extra check fns (e.g. PDF tamper signals, Layer 3)
    Returns (results, band).
    """
    context = {"ocr": ocr_analysis}
    checks = list(STATEMENT_CHECKS_FROM_RECON) + list(extra_checks or [])
    return run_checks(checks, extracted={}, context=context)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _recon(context):
    ocr = context.get("ocr")
    return getattr(ocr, "reconciliation", None) if ocr else None


def _name_check(match, *, code, label, pass_detail, fail_detail, missing_detail):
    """
    Translate a NameMatchResult into a CheckResult.
    NameMatchResult has `.is_flag` (bool) and `.band` (NameMatchBand, incl.
    NOT_FOUND). A None match means reconcile() didn't run that comparison
    (e.g. no name on the doc, or no profile/id name supplied).
    """
    if match is None:
        return CheckResult(code, label, Outcome.INCONCLUSIVE, "moderate",
                           missing_detail)
    # NOT_FOUND band -> couldn't read a name to compare (inconclusive, not fail).
    band = getattr(match, "band", None)
    band_name = getattr(band, "name", str(band)) if band is not None else ""
    if band_name == "NOT_FOUND":
        return CheckResult(code, label, Outcome.INCONCLUSIVE, "moderate",
                           missing_detail)
    if getattr(match, "is_flag", False):
        return CheckResult(code, label, Outcome.FAIL, "moderate", fail_detail)
    return CheckResult(code, label, Outcome.PASS, "moderate", pass_detail)