"""
Fedha-Grow — Tesseract OCR adapter
==================================
Local OCR using Tesseract (no data leaves the server — important for the
Data Protection Act posture). Reads a PDF or image file into raw text, then
hands off to the statement parser and reconciliation.

System requirements (install once):
    apt-get install tesseract-ocr poppler-utils
    pip install pytesseract pdf2image pillow rapidfuzz

This is a real, working adapter — NOT a stub. The one provisional piece is the
statement parser it calls (parser.py), whose regexes you tune to your banks.

Degrades safely: unreadable scans/photos yield low-confidence text, which the
downstream logic treats as "unverified", never as "borrower lied".
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import os

from .parser import parse_statement, ParsedStatement
from .reconciliation import reconcile, ReconciliationResult


@dataclass
class OCRAnalysis:
    text_len: int
    ocr_confidence: str                 # low | medium | high
    statement: ParsedStatement
    reconciliation: ReconciliationResult = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class TesseractDocumentAdapter:
    """
    provider_name matches the integrations registry category 'document_analysis'.
    Enable by pointing settings.INTEGRATIONS['document_analysis']['adapter'] here.
    """
    provider_name = "tesseract-local"

    def __init__(self, lang: str = "eng", dpi: int = 300, **kwargs):
        self.lang = lang
        self.dpi = dpi

    # ---- public ----
    def analyse_statement(
        self, file_path: str, *,
        declared_expenses: Decimal = Decimal("0"),
        profile_name: str = "", id_name: str = "",
    ) -> OCRAnalysis:
        try:
            text = self._ocr_file(file_path)
        except Exception as exc:  # noqa: BLE001
            return OCRAnalysis(text_len=0, ocr_confidence="low",
                               statement=ParsedStatement(note="OCR failed."),
                               error=f"{type(exc).__name__}: {exc}")

        conf = "high" if len(text) > 1500 else "medium" if len(text) > 400 else "low"
        statement = parse_statement(text)
        recon = reconcile(
            declared_expenses=declared_expenses,
            statement=statement,
            profile_name=profile_name,
            id_name=id_name,
        )
        return OCRAnalysis(
            text_len=len(text), ocr_confidence=conf,
            statement=statement, reconciliation=recon,
        )

    def read_name(self, file_path: str) -> str:
        """OCR an ID copy (or any doc) and return the best-guess name line."""
        try:
            text = self._ocr_file(file_path)
        except Exception:  # noqa: BLE001
            return ""
        from .parser import _extract_name
        return _extract_name([ln for ln in text.splitlines() if ln.strip()])

    # ---- internals ----
    def _ocr_file(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self._ocr_pdf(file_path)
        return self._ocr_image(file_path)

    def _ocr_image(self, file_path: str) -> str:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(file_path), lang=self.lang)

    def _ocr_pdf(self, file_path: str) -> str:
        import pytesseract
        from pdf2image import convert_from_path
        pages = convert_from_path(file_path, dpi=self.dpi)
        return "\n".join(pytesseract.image_to_string(p, lang=self.lang) for p in pages)