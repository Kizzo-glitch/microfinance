"""
Payslip parser — label-based, FAIL HONEST.

Payslips have no standard layout, so this looks for LABELLED figures (Gross,
Net, Deductions/PAYE, employer, name). If it can't confidently find gross AND
net, it reports is_parseable=False — it NEVER guesses which number is which.
A payslip it can't read bands as 'unverifiable' downstream, not as a wrong
income figure fed into affordability.

Mirrors parse_statement()'s shape: a dataclass with the figures + a
parse_confidence, consumed by the doccheck layer.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Reuse the same money shape as the statement parser.
_MONEY = r"(?:M|R|LSL|ZAR)?\s?-?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?"
_MONEY_RE = re.compile(_MONEY)

# Labels, most-specific first. Each maps to a field; we take the LAST money
# token on a matching line (the amount usually sits at the line's end).
_GROSS_LABELS = re.compile(r"\b(gross\s*(?:pay|salary|earnings|income)?|total\s*earnings)\b", re.I)
_NET_LABELS   = re.compile(r"\b(net\s*(?:pay|salary|income)?|take[\s-]*home|amount\s*payable)\b", re.I)
# Prefer an explicit TOTAL deductions line; only fall back to component lines
# (PAYE/tax/pension) if no total is present. Matching a component as if it were
# the total would break the gross - deductions = net check on genuine payslips.
_DED_TOTAL_LABELS = re.compile(r"\b(total\s*deductions?|deductions?\s*total|total\s*deduction)\b", re.I)
_DED_COMPONENT_LABELS = re.compile(r"\b(paye|tax|pension|nssa)\b", re.I)
_EMPLOYER_LBL = re.compile(r"\b(employer|company|organisation|organization)\s*(?:name)?\s*[:\-]\s*(.+)", re.I)
_NAME_LBL     = re.compile(r"\b(employee\s*name|name\s*of\s*employee|employee|name)\s*[:\-]\s*(.+)", re.I)


@dataclass
class ParsedPayslip:
    employee_name: str = ""
    employer_name: str = ""
    gross: Decimal = None
    net: Decimal = None
    total_deductions: Decimal = None
    # True only when we read an explicit "Total deductions" line (not a single
    # component like PAYE). The gross-deductions=net check should only run when
    # this is True — otherwise we'd compare against a partial deductions figure.
    deductions_is_total: bool = False
    parse_confidence: str = "low"     # low | medium | high
    note: str = ""

    @property
    def is_parseable(self) -> bool:
        # Honest bar: we need BOTH gross and net to say anything about a payslip.
        return self.gross is not None and self.net is not None


def _to_decimal(token: str):
    cleaned = re.sub(r"[^\d.\-]", "", (token or "").replace(",", ""))
    if cleaned in ("", "-", "."):
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _last_money_on(line: str):
    monies = _MONEY_RE.findall(line)
    monies = [m for m in monies if any(c.isdigit() for c in m)]
    if not monies:
        return None
    return _to_decimal(monies[-1])


def _labelled_value(lines, label_re):
    """First money value on a line whose text matches label_re."""
    for ln in lines:
        if label_re.search(ln):
            val = _last_money_on(ln)
            if val is not None and val > 0:
                return val
    return None


def _labelled_text(lines, label_re):
    for ln in lines[:30]:
        m = label_re.search(ln)
        if m:
            cand = m.groups()[-1].strip()
            cand = re.sub(r"[^A-Za-z0-9\s.'&-]", "", cand).strip()
            if cand and not cand.isdigit():
                return cand[:120]
    return ""


def parse_payslip(ocr_text: str) -> ParsedPayslip:
    if not ocr_text or not ocr_text.strip():
        return ParsedPayslip(note="No text extracted from document.")

    lines = [ln for ln in ocr_text.splitlines() if ln.strip()]

    gross = _labelled_value(lines, _GROSS_LABELS)
    net   = _labelled_value(lines, _NET_LABELS)
    # Prefer an explicit "Total deductions" line; fall back to a component only
    # if no total exists (and mark lower confidence in that case).
    ded = _labelled_value(lines, _DED_TOTAL_LABELS)
    ded_is_total = ded is not None
    if ded is None:
        ded = _labelled_value(lines, _DED_COMPONENT_LABELS)

    employee = _labelled_text(lines, _NAME_LBL)
    employer = _labelled_text(lines, _EMPLOYER_LBL)

    # Confidence: high when we have gross+net+deductions+a name; medium with
    # gross+net; low otherwise (not parseable).
    if gross is not None and net is not None and ded is not None and employee:
        conf = "high"
    elif gross is not None and net is not None:
        conf = "medium"
    else:
        conf = "low"

    note = ("Read gross/net from labels."
            if gross is not None and net is not None
            else "Could not find labelled Gross and Net figures — treat as unparsed.")

    return ParsedPayslip(
        employee_name=employee,
        employer_name=employer,
        gross=gross, net=net, total_deductions=ded,
        deductions_is_total=ded_is_total,
        parse_confidence=conf, note=note,
    )