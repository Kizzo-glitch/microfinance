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



"""
Layer 4 — payslip internal checks.
Layer 5 — cross-document: payslip salary vs a recurring statement credit.

All honest: when a figure can't be read, the check is INCONCLUSIVE (the doc then
bands 'unverifiable'), never a false fail or a confident-but-wrong number.

Shaped like the other checks ((extracted, context) -> CheckResult) so they slot
into run_checks / assess_*.
"""

from decimal import Decimal
from integrations.verification.doccheck.framework import CheckResult, Outcome

CENT = Decimal("0.01")
TOLERANCE = Decimal("1.00")   # allow M1 for OCR rounding on payslip arithmetic


# ── Layer 4: internal payslip checks ───────────────────────────────────────

def check_payslip_math(extracted, context):
    """
    STRONG. gross - total_deductions == net. Only runs when we have an explicit
    TOTAL deductions figure (not a single component), else inconclusive.
    """
    p = context.get("payslip")
    if p is None or not p.is_parseable:
        return CheckResult(
            "payslip_math", "Payslip figures add up",
            Outcome.INCONCLUSIVE, "strong",
            "Could not read the payslip's gross/net figures to check them.")

    if p.total_deductions is None or not getattr(p, "deductions_is_total", False):
        return CheckResult(
            "payslip_math", "Payslip figures add up",
            Outcome.INCONCLUSIVE, "strong",
            "No explicit 'Total deductions' line was read, so gross − deductions "
            "= net can't be checked.")

    expected_net = (p.gross - p.total_deductions).quantize(CENT)
    if abs(expected_net - p.net) > TOLERANCE:
        return CheckResult(
            "payslip_math", "Payslip figures add up",
            Outcome.FAIL, "strong",
            detail=(f"The payslip's own figures don't add up: gross M{p.gross} "
                    f"minus deductions M{p.total_deductions} = M{expected_net}, "
                    f"but net pay shows M{p.net}."))

    return CheckResult(
        "payslip_math", "Payslip figures add up",
        Outcome.PASS, "strong",
        f"Gross M{p.gross} − deductions M{p.total_deductions} = net M{p.net}.")


def check_payslip_name(extracted, context):
    """
    MODERATE. Payslip employee name vs the borrower's profile name. Reuses the
    same fuzzy matcher the statement path uses (match_names).
    """
    p = context.get("payslip")
    profile_name = context.get("profile_name", "")
    if p is None or not p.employee_name:
        return CheckResult(
            "payslip_name", "Payslip name matches profile",
            Outcome.INCONCLUSIVE, "moderate",
            "No employee name was read on the payslip.")
    if not profile_name:
        return CheckResult(
            "payslip_name", "Payslip name matches profile",
            Outcome.INCONCLUSIVE, "moderate",
            "No profile name available to compare.")

    match = _match(profile_name, p.employee_name, context)
    if match is None:
        return CheckResult(
            "payslip_name", "Payslip name matches profile",
            Outcome.INCONCLUSIVE, "moderate",
            "Could not compare the names.")
    if getattr(match, "is_flag", False):
        return CheckResult(
            "payslip_name", "Payslip name matches profile",
            Outcome.FAIL, "moderate",
            f"The payslip name ('{p.employee_name}') doesn't match the "
            f"borrower's profile name.")
    return CheckResult(
        "payslip_name", "Payslip name matches profile",
        Outcome.PASS, "moderate",
        "The payslip name matches the borrower's profile.")


PAYSLIP_CHECKS = [check_payslip_math, check_payslip_name]


# ── Layer 5: cross-document (payslip ↔ statement) ──────────────────────────

def check_salary_lands_in_account(extracted, context):
    """
    STRONG(ish). Does the payslip's NET pay roughly match a CREDIT seen on the
    bank statement? This is the "does the claimed income actually arrive"
    signal. Honest about its limits: the statement parser tags credits only by
    keyword, so we look for ANY inflow within tolerance of net pay.

    Needs BOTH a parsed payslip (net) and a parsed statement (credits).
    """
    p = context.get("payslip")
    stmt = context.get("statement")
    if p is None or p.net is None:
        return CheckResult(
            "salary_lands", "Salary appears in the bank account",
            Outcome.INCONCLUSIVE, "strong",
            "No net-pay figure on the payslip to look for.")
    if stmt is None or not getattr(stmt, "transactions", None):
        return CheckResult(
            "salary_lands", "Salary appears in the bank account",
            Outcome.INCONCLUSIVE, "strong",
            "No readable bank statement to match the salary against.")

    net = p.net
    # Tolerance: salary may arrive minus small bank charges, or the payslip
    # 'net' differs slightly from the deposit. Allow 5% either way.
    lo = net * Decimal("0.95")
    hi = net * Decimal("1.05")

    inflows = [t for t in stmt.transactions if not getattr(t, "is_outflow", True)]
    near = [t for t in inflows if lo <= Decimal(str(getattr(t, "amount", 0))) <= hi]

    if near:
        amt = Decimal(str(near[0].amount))
        return CheckResult(
            "salary_lands", "Salary appears in the bank account",
            Outcome.PASS, "strong",
            f"A credit of about M{amt} on the statement matches the payslip's "
            f"net pay of M{net}.")

    # No matching credit found. Honest nuance: this is a FLAG, but a moderate
    # one — the statement period may not cover a pay date, or the parser missed
    # a credit. Not proof of fraud, but worth the lender's eye.
    return CheckResult(
        "salary_lands", "Salary appears in the bank account",
        Outcome.FAIL, "moderate",
        detail=(f"No credit close to the payslip's net pay (M{net}) was found "
                f"on the bank statement. The income on the payslip may not be "
                f"landing in this account, or the statement doesn't cover a pay "
                f"date — worth checking."))



# ── helpers ────────────────────────────────────────────────────────────────

def _match(a, b, context):
    """Use the project's name matcher if provided in context, else a simple one."""
    matcher = context.get("match_names")
    if matcher:
        try:
            return matcher(a, b)
        except Exception:
            return None
    # Fallback: crude case-insensitive token overlap -> object with .is_flag.
    class _M:
        def __init__(self, flag): self.is_flag = flag
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    overlap = len(ta & tb)
    return _M(overlap < 1)