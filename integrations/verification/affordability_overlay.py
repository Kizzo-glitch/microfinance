from integrations.verification.doccheck.framework import BAND_LABELS
# Which document type backs which affordability input. A borrower's income
# evidence is normally the bank statement (salary credits) and/or payslip;
# expenses are cross-checked against statement outflows.
INCOME_DOC_TYPES = {"bank_statement", "payslip"}
EXPENSE_DOC_TYPES = {"bank_statement"}

# Bands that should make a lender pause on figures that document supported.
WEAK_BANDS = {"flagged", "low", "unverifiable"}

'''
def build_affordability_overlay(application):
    """
    Returns a dict the review template renders NEXT TO the frozen affordability
    snapshot. Never mutates the snapshot.

    {
      'has_checks': bool,                 # any document checked at all?
      'income_support': [ {doc_type, band, band_label, tone, concerning}, ... ],
      'expense_support': [ ... ],
      'concern': bool,                    # any supporting doc is weak/flagged
      'note': str,                        # one-line human summary
    }
    """
    from integrations.verification.doccheck.framework import BAND_LABELS

    income_support = []
    expense_support = []

    # Latest check run per checkable document on this application.
    for doc in application.loan_documents.all():
        latest = doc.check_runs.first()
        if latest is None:
            continue
        dt = (doc.document_type or "").lower()
        entry = {
            "doc_type": doc.get_document_type_display(),
            "band": latest.band,
            "band_label": BAND_LABELS.get(latest.band, latest.band),
            "tone": latest.band_tone,
            "concerning": latest.band in WEAK_BANDS,
        }
        if dt in INCOME_DOC_TYPES:
            income_support.append(entry)
        if dt in EXPENSE_DOC_TYPES:
            expense_support.append(entry)

    has_checks = bool(income_support or expense_support)
    concern = any(e["concerning"] for e in income_support + expense_support)

    if not has_checks:
        note = ("No document checks have been run yet, so the figures behind "
                "this affordability assessment are unverified.")
    elif concern:
        note = ("Some documents behind these figures were flagged or could not "
                "be verified. Weigh the affordability result with that in mind.")
    else:
        note = ("The documents behind these figures passed their checks.")

    return {
        "has_checks": has_checks,
        "income_support": income_support,
        "expense_support": expense_support,
        "concern": concern,
        "note": note,
    }'''


"""
build_affordability_overlay — now attaches the short flag reasons to each
document entry, so the overlay can say WHAT was flagged, not just the band.

Only change vs the original: import flag_reasons_for_run, and add
"reasons": flag_reasons_for_run(latest) to each entry. `latest` (the check run
with its .results) is already in scope, so this is no extra query/computation.
"""

def build_affordability_overlay(application):
    """
    Returns a dict the review template renders NEXT TO the frozen affordability
    snapshot. Never mutates the snapshot.

    {
      'has_checks': bool,
      'income_support': [ {doc_type, band, band_label, tone, concerning, reasons}, ... ],
      'expense_support': [ ... ],
      'concern': bool,
      'note': str,
    }

    Each entry's `reasons` is a list of {severity, text, detail} for every FAIL
    and INCONCLUSIVE check on that document (empty when the doc passed clean).
    """


    income_support = []
    expense_support = []

    for doc in application.loan_documents.all():
        latest = doc.check_runs.first()
        if latest is None:
            continue
        dt = (doc.document_type or "").lower()
        entry = {
            "doc_type": doc.get_document_type_display(),
            "band": latest.band,
            "band_label": BAND_LABELS.get(latest.band, latest.band),
            "tone": latest.band_tone,
            "concerning": latest.band in WEAK_BANDS,
            # NEW: short lender-facing reasons for each FAIL/INCONCLUSIVE check.
            "reasons": flag_reasons_for_run(latest),
        }
        if dt in INCOME_DOC_TYPES:
            income_support.append(entry)
        if dt in EXPENSE_DOC_TYPES:
            expense_support.append(entry)

    has_checks = bool(income_support or expense_support)
    concern = any(e["concerning"] for e in income_support + expense_support)

    if not has_checks:
        note = ("No document checks have been run yet, so the figures behind "
                "this affordability assessment are unverified.")
    elif concern:
        note = ("Some documents behind these figures were flagged or could not "
                "be verified. Weigh the affordability result with that in mind.")
    else:
        note = ("The documents behind these figures passed their checks.")

    return {
        "has_checks": has_checks,
        "income_support": income_support,
        "expense_support": expense_support,
        "concern": concern,
        "note": note,
    }



"""
Short, lender-facing reasons for flagged/inconclusive checks — for the
affordability overlay ("Are these figures backed up?").

The band pill already says "Medium confidence — minor flags"; this turns each
underlying check into a one-line reason so the lender sees WHAT was flagged
without opening the full Document-checks panel.

No new computation — it reads the frozen DocumentCheckRun.results that each run
already stores: a list of {code, label, outcome, strength, detail}.

Short reasons come from a code->text map (codes are stable). Any code not in the
map falls back to the check's own `label`, so a new check still shows something
sensible rather than nothing.
"""

# Stable check codes -> short reason shown under the pill.
# Phrased as the ISSUE, not the check name (the lender wants "what's wrong").
_FAIL_REASONS = {
    "expense_coverage": "Declared expenses below spending seen on the statement",
    "statement_name":   "Statement account-holder name doesn't match the borrower",
    "id_name":          "ID name doesn't match the borrower's profile",
    "payslip_math":     "Payslip figures don't add up (gross − deductions ≠ net)",
    "payslip_name":     "Payslip name doesn't match the borrower's profile",
    "salary_lands":     "Payslip salary not found as a credit on the statement",
    "parse_confidence": "Document read poorly — checks less reliable",
}

# INCONCLUSIVE = couldn't verify (not a found problem). Phrased as "couldn't check".
_INCONCLUSIVE_REASONS = {
    "expense_coverage": "Couldn't verify declared expenses against the statement",
    "statement_name":   "Couldn't read a name on the statement to cross-check",
    "id_name":          "No ID name available to cross-check",
    "payslip_math":     "No explicit 'Total deductions' line — couldn't check the math",
    "payslip_name":     "No employee name read on the payslip to cross-check",
    "salary_lands":     "Couldn't match salary to a statement credit",
    "parse_confidence": "Document read poorly — a clearer copy would help",
}


def flag_reasons_for_run(run):
    """
    Given a DocumentCheckRun (or its .results list), return a list of short
    reasons for every FAIL and INCONCLUSIVE result, newest issues first:

        [{"severity": "fail"|"inconclusive", "text": "<short reason>",
          "detail": "<the full detail string, for a tooltip/title>"}]

    PASS results are omitted (nothing to surface).
    """
    results = getattr(run, "results", None)
    if results is None:
        results = run if isinstance(run, (list, tuple)) else []

    out = []
    for r in results:
        code = (r.get("code") or "").strip()
        outcome = (r.get("outcome") or "").upper()
        label = r.get("label") or code
        detail = r.get("detail") or ""

        if outcome == "FAIL":
            text = _FAIL_REASONS.get(code, label)
            out.append({"severity": "fail", "text": text, "detail": detail})
        elif outcome == "INCONCLUSIVE":
            text = _INCONCLUSIVE_REASONS.get(code, label)
            out.append({"severity": "inconclusive", "text": text, "detail": detail})
        # PASS -> skip

    # FAIL first (real issues), then inconclusive.
    out.sort(key=lambda x: 0 if x["severity"] == "fail" else 1)
    return out