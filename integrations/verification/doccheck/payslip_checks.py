"""
Layer 4 — payslip internal checks.
Layer 5 — cross-document: payslip salary vs a recurring statement credit.

All honest: when a figure can't be read, the check is INCONCLUSIVE (the doc then
bands 'unverifiable'), never a false fail or a confident-but-wrong number.

Shaped like the other checks ((extracted, context) -> CheckResult) so they slot
into run_checks / assess_*.
"""

from decimal import Decimal
from .framework import CheckResult, Outcome

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