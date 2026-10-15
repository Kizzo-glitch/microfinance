"""
Fedha-Grow — integrations service facade
========================================
Thin, friendly entry points so application code never touches adapters or the
registry directly. Import these, not the internals.

    from integrations.services import verify_identity, check_credit_bureau, initiate_payment

Every call works today: with no provider connected it returns a PENDING result,
which callers must treat as "not verified / not settled" — never as success.
"""

from decimal import Decimal
from .registry import get_adapter
from .base import VerificationResult, PaymentResult


# ---- verification -------------------------------------------------
def verify_identity(national_id: str, **kwargs) -> VerificationResult:
    """Government identity (Home Affairs) check."""
    return get_adapter("government_identity").check(national_id, **kwargs)


def check_credit_bureau(identifier: str, **kwargs) -> VerificationResult:
    """Credit-bureau lookup."""
    return get_adapter("credit_bureau").check(identifier, **kwargs)


# ---- payment ------------------------------------------------------
def initiate_payment(category: str, *, amount: Decimal, reference: str,
                     payer=None, payee=None, **kwargs) -> PaymentResult:
    """
    Start an outbound payment on a rail: 'mobile_money', 'bank',
    or 'payment_provider'.
    """
    return get_adapter(category).initiate(
        amount=amount, reference=reference, payer=payer, payee=payee, **kwargs
    )

"""
Layer 6 — the verification service (place in integrations/verification/).

The ONE bridge: it touches Django (reads the BorrowerDocs file, writes a
DocumentCheckRun) AND the pure engine (assess_statement + pdf_signal_checks).
The doccheck package itself stays Django-free; all the Django-aware glue is here.

Flow when the lender clicks "Run checks":
    file -> OCR (your TesseractDocumentAdapter) -> assess_statement()
         -> (+ PDF signals if it's a PDF) -> freeze a DocumentCheckRun row.
"""

from dataclasses import asdict, is_dataclass

from django.utils import timezone

# pure engine
from integrations.verification.doccheck.framework import BAND_LABELS, Outcome
from integrations.verification.doccheck.wrap_reconcile import assess_statement
from integrations.verification.doccheck.pdf_signals import (
    pdf_signal_checks, is_pdf,
)

# your existing OCR adapter
from integrations.verification.documents.ocr import TesseractDocumentAdapter  

# the model from Layer 6
from borrowers.models import DocumentCheckRun   


def run_document_checks(document, *, run_by=None,
                        declared_expenses=None,
                        profile_name="", id_name=""):
    """
    document : a BorrowerDocs instance (has a FileField — adjust `.file` below)
    run_by   : the User who triggered this (for the audit trail)

    Returns the created DocumentCheckRun. Always creates a NEW row (never edits
    an old one) so each run is an immutable record of what was assessed.
    """
    # BorrowerDocs.file is a FileField.
    file_field = getattr(document, "file", None)
    file_path = file_field.path if file_field else None

    doc_type = _map_doc_type(document)

    # --- 1. OCR + your reconcile ---
    adapter = TesseractDocumentAdapter()
    ocr = adapter.analyse_statement(
        file_path,
        declared_expenses=declared_expenses or 0,
        profile_name=profile_name,
        id_name=id_name,
    )

    # --- 2. PDF structural signals, only for native PDFs ---
    extra = []
    pdf_ran = False
    if file_path and is_pdf(file_path):
        extra = pdf_signal_checks(file_path)
        pdf_ran = True

    # --- 3. run the pure engine ---
    results, band = assess_statement(ocr, extra_checks=extra)

    # --- 4. freeze the result as data ---
    results_data = [_result_to_dict(r) for r in results]
    flag_count = sum(1 for r in results if r.outcome == Outcome.FAIL)
    inconclusive_count = sum(1 for r in results if r.outcome == Outcome.INCONCLUSIVE)

    run = DocumentCheckRun.objects.create(
        document=document,
        doc_type=doc_type,
        band=band,
        results=results_data,
        flag_count=flag_count,
        inconclusive_count=inconclusive_count,
        run_by=run_by,
        run_at=timezone.now(),
        meta={
            "band_label": BAND_LABELS.get(band, band),
            "ocr_confidence": getattr(ocr, "ocr_confidence", None),
            "pdf_signals_ran": pdf_ran,
            "ocr_ok": getattr(ocr, "ok", None),
            "ocr_error": getattr(ocr, "error", "") or "",
        },
    )
    return run


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _result_to_dict(r):
    """CheckResult (a dataclass) -> plain dict for JSONField. Enum -> str."""
    if is_dataclass(r):
        d = asdict(r)
    else:
        d = dict(r)
    out = d.get("outcome")
    d["outcome"] = out.value if hasattr(out, "value") else out
    return d


def _map_doc_type(document):
    """
    Map BorrowerDocs.document_type -> our DocumentCheckRun.doc_type choices.
    Your real values: 'bank_statement', 'payslip', 'id_proof', plus business
    docs we don't assess here.
    """
    raw = (getattr(document, "document_type", "") or "").lower()
    if raw == "bank_statement":
        return "bank_statement"
    if raw == "payslip":
        return "payslip"
    if raw == "id_proof":
        return "national_id"
    return "other"