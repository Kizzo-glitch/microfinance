"""
Fedha-Grow — bank statement parser
===================================
Turns raw OCR text into structured data: candidate account-holder name and a
list of transactions (date, description, amount, direction).

IMPORTANT — this is the PROVIDER-SPECIFIC part.
Bank statement layouts differ between banks, so this is a general-purpose parser
tuned against common patterns. Calibrate the regexes against real statements from
the specific Lesotho banks your borrowers use. The interface (parse_statement ->
ParsedStatement) is stable; the internals are the bit you refine.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re


@dataclass
class Transaction:
    raw: str
    amount: Decimal
    is_outflow: bool
    description: str = ""
    date: str = ""


@dataclass
class ParsedStatement:
    account_holder: str = ""
    transactions: list = field(default_factory=list)
    total_outflows: Decimal = Decimal("0.00")
    total_inflows: Decimal = Decimal("0.00")
    parse_confidence: str = "low"      # low | medium | high
    note: str = ""

    @property
    def is_parseable(self) -> bool:
        return len(self.transactions) > 0


# Money like 1,234.56 or 1234.56 (optionally with a leading M / R / currency)
_MONEY = r"(?:M|R|LSL|ZAR)?\s?-?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})"
_MONEY_RE = re.compile(_MONEY)
_DATE_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})\b")

# Words that suggest money leaving the account (tune per bank).
_DEBIT_HINTS = re.compile(
    r"\b(debit|dr|withdraw|payment|purchase|pos|transfer out|"
    r"loan|repay|installment|instalment|fee|charge|airtime|"
    r"eft|ach|debit order|stop order)\b", re.I,
)
_CREDIT_HINTS = re.compile(
    r"\b(credit|cr|deposit|salary|wage|transfer in|received|refund)\b", re.I,
)

# Labels a bank prints before the account holder's name.
_NAME_LABELS = re.compile(
    r"(?:account\s*(?:holder|name)|customer\s*name|name)\s*[:\-]\s*(.+)", re.I,
)


def _to_decimal(token: str) -> Decimal:
    cleaned = re.sub(r"[^\d.\-]", "", token.replace(",", ""))
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _extract_name(lines: list[str]) -> str:
    # 1) explicit label
    for ln in lines[:25]:
        m = _NAME_LABELS.search(ln)
        if m:
            candidate = m.group(1).strip()
            # keep it to a plausible name (letters, spaces, a few tokens)
            candidate = re.sub(r"[^A-Za-z\s.'-]", "", candidate).strip()
            if 1 < len(candidate.split()) <= 5:
                return candidate
    # 2) fallback: an ALL-CAPS line near the top that looks like a name
    for ln in lines[:15]:
        s = ln.strip()
        if (2 <= len(s.split()) <= 4
                and s.isupper()
                and re.fullmatch(r"[A-Z\s.'-]+", s)):
            return s.title()
    return ""


def parse_statement(ocr_text: str) -> ParsedStatement:
    if not ocr_text or not ocr_text.strip():
        return ParsedStatement(parse_confidence="low", note="No text extracted from document.")

    lines = [ln for ln in ocr_text.splitlines() if ln.strip()]
    holder = _extract_name(lines)

    txns: list[Transaction] = []
    for ln in lines:
        monies = _MONEY_RE.findall(ln)
        if not monies:
            continue
        # last money token on a line is usually the transaction amount
        amount = _to_decimal(monies[-1])
        if amount == 0:
            continue

        is_out = bool(_DEBIT_HINTS.search(ln))
        is_in = bool(_CREDIT_HINTS.search(ln))
        # if ambiguous, a leading minus or "-" signals outflow
        if not is_out and not is_in:
            is_out = "-" in monies[-1]

        date_m = _DATE_RE.search(ln)
        desc = _MONEY_RE.sub("", ln)
        desc = _DATE_RE.sub("", desc).strip(" \t-|:")

        txns.append(Transaction(
            raw=ln.strip(),
            amount=abs(amount),
            is_outflow=is_out if (is_out or is_in) else True,  # default outflow if unknown
            description=desc[:120],
            date=date_m.group(1) if date_m else "",
        ))

    total_out = sum((t.amount for t in txns if t.is_outflow), Decimal("0.00"))
    total_in = sum((t.amount for t in txns if not t.is_outflow), Decimal("0.00"))

    # crude confidence: more structured signal -> higher confidence
    if len(txns) >= 8 and holder:
        conf = "high"
    elif len(txns) >= 3:
        conf = "medium"
    else:
        conf = "low"

    return ParsedStatement(
        account_holder=holder,
        transactions=txns,
        total_outflows=total_out.quantize(Decimal("0.01")),
        total_inflows=total_in.quantize(Decimal("0.01")),
        parse_confidence=conf,
        note=f"Parsed {len(txns)} transaction line(s).",
    )