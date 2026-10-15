"""
Layer 7 — affordability VERIFICATION OVERLAY.

Does NOT recompute or touch the frozen affordability snapshot. The snapshot is
the record as issued at submission and stays exactly as it was.

What this does: for the figures the affordability snapshot RELIED ON (declared
income, declared expenses), report whether the documents those figures came from
were LATER verified, flagged, or unverifiable when the lender ran checks. So the
lender sees, beside the frozen verdict, whether its inputs held up — without
anyone rewriting the record.

Honest framing:
  - "Affordability was assessed on <submitted figures>." (the snapshot)
  - "Those figures' supporting documents: statement = <band>, payslip = <band>."
    (this overlay)
A 'flagged' or 'unverifiable' supporting document means the lender should weigh
the frozen affordability verdict more cautiously — it does NOT silently change
the number.
"""

# Which document type backs which affordability input. A borrower's income
# evidence is normally the bank statement (salary credits) and/or payslip;
# expenses are cross-checked against statement outflows.
INCOME_DOC_TYPES = {"bank_statement", "payslip"}
EXPENSE_DOC_TYPES = {"bank_statement"}

# Bands that should make a lender pause on figures that document supported.
WEAK_BANDS = {"flagged", "low", "unverifiable"}


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
    }