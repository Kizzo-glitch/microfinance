
from borrowers.models import ExpenseAnalysis, BorrowerDocs
from loans.loan_terms_resolver import effective_rate, effective_terms
from loans.models import Loan

from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP

from loans.models import Loan, ResponsibleLendingAssessment
from borrowers.models import BorrowerDocs, ExpenseAnalysis


 
# =====================================================================
# 1. POLICY — all thresholds in one place, easy to tune and to explain
#    to a regulator. Percentages are of gross monthly income.
# =====================================================================
class AFFORDABILITY_POLICY:
    # Installment-to-income (the NEW loan alone)
    ITI_COMFORTABLE = Decimal("30")   # <=30% of income -> comfortable
    ITI_TIGHT       = Decimal("40")   # 30-40% -> tight; >40% -> unaffordable
 
    # Total debt-to-income (new installment + existing loan installments)
    DTI_CEILING     = Decimal("45")   # above this -> unaffordable regardless
 
    # Disposable-income buffer: what's left after everything, as % of income
    BUFFER_MIN      = Decimal("10")   # left with <10% of income -> tight
 
    # The band we solve backwards from when recommending a max amount
    TARGET_ITI      = Decimal("30")   # recommend loans that land at/under this
 
 
TWO_DP = Decimal("0.01")
 
 
def _money(value) -> Decimal:
    """Quantize to 2 decimal places, safely handling None/0."""
    return (Decimal(value or 0)).quantize(TWO_DP, rounding=ROUND_HALF_UP)

 
# =====================================================================
# 3. THE ENGINE
# =====================================================================
class AffordabilityAdvisor:
    """
    Computes affordability for a loan application and produces borrower-facing
    recommendations. Pure computation on build(); persistence is explicit via
    snapshot() so GET can advise without writing an audit record.
    """
 
    ENGINE_VERSION = "2.0"
 
    def __init__(self, loan_application):
        self.app = loan_application
        self.borrower = loan_application.borrower
        self.lender = loan_application.lender
        self.product = getattr(loan_application, "product", None)
        # Set True by _recommend() when no amount/term at THIS lender fits,
        # signalling the borrower should consider a different lender.
        self._needs_other_lender = False
 
    # ---- public API -------------------------------------------------
    def build(self) -> dict:
        """Compute the full advisory result. Does NOT persist."""
        # Route month-end products first — they don't use the instalment model.
        if self.product and getattr(self.product, "repayment_structure", "") == "single_month_end":
            return self._build_single_repayment()

        income   = _money(getattr(self.borrower, "income", 0))
        expenses = self._sum_expenses()
        existing_commitments, active_loans = self._existing_exposure()
        installment = _money(self.app.monthly_installment)
 
        # Guard: no declared income means we cannot assess affordability.
        if income <= 0:
            return self._not_assessable(income, expenses, installment,
                                        existing_commitments, active_loans)
 
        disposable_before = income - expenses - existing_commitments
        disposable_after  = disposable_before - installment
 
        iti = self._pct(installment, income)                       # new loan only
        dti = self._pct(installment + existing_commitments, income)  # total debt load
        affordability_index_after = self._pct(disposable_after, income)
 
        outcome = self._classify(iti, dti, disposable_after, income)
 
        rec_max, rec_term, advice = self._recommend(
            outcome=outcome, income=income, disposable_before=disposable_before,
            existing_commitments=existing_commitments, installment=installment,
        )
 
        return {
            "income": income,
            "expenses": expenses,
            "existing_monthly_commitments": existing_commitments,
            "existing_active_loans": active_loans,
            "installment": installment,
            "disposable_before": disposable_before,
            "disposable_after": disposable_after,
            "installment_to_income": iti,
            "debt_to_income_ratio": dti,
            "affordability_index_after": affordability_index_after,
            "outcome": outcome,
            "recommended_max_loan": rec_max,
            "recommended_term": rec_term,
            "advice": advice,
            "needs_other_lender": self._needs_other_lender,
            "lender_terms": self._sorted_terms(),
            "assessable": True,
        }
 
    def snapshot(self, result: dict = None, reconciliation=None) -> ResponsibleLendingAssessment:
        """
        Create the immutable audit record. Call ONLY at submission.
        Refuses to overwrite an existing assessment for this application.

        `reconciliation` is an optional ReconciliationResult from OCR document
        analysis; when present, its review signals are stored on the snapshot.
        """
        if hasattr(self.app, "affordability_assessment"):
            return self.app.affordability_assessment  # already snapshotted

        r = result or self.build()
        doc = self._reconciliation_fields(reconciliation)

        return ResponsibleLendingAssessment.objects.create(
            borrower=self.borrower,
            lender=self.lender,
            loan_application=self.app,
            monthly_income=r["income"],
            monthly_expenses=r["expenses"],
            existing_monthly_commitments=r["existing_monthly_commitments"],
            monthly_installment=r["installment"],
            disposable_income_before=r["disposable_before"],
            disposable_income_after=r["disposable_after"],
            installment_to_income=r["installment_to_income"],
            debt_to_income_ratio=r["debt_to_income_ratio"],
            affordability_index_after=r["affordability_index_after"],
            existing_active_loans=r["existing_active_loans"],
            outcome=r["outcome"],
            recommended_max_loan=r["recommended_max_loan"],
            recommended_term=r["recommended_term"],
            advice=r["advice"],
            engine_version=self.ENGINE_VERSION,
            **doc,
        )

    @staticmethod
    def _reconciliation_fields(reconciliation) -> dict:
        """Map an optional ReconciliationResult onto snapshot fields."""
        if reconciliation is None:
            return {}
        name_flag = any(
            m and m.is_flag
            for m in (reconciliation.statement_name_match, reconciliation.id_name_match)
        )
        return {
            "expenses_verified": bool(reconciliation.observed_outflows and reconciliation.observed_outflows > 0),
            "observed_outflows": reconciliation.observed_outflows,
            "expense_discrepancy_flag": reconciliation.expense_flag,
            "name_match_flag": name_flag,
            "review_signals": list(reconciliation.signals or []),
        }
    
    # ---- internals --------------------------------------------------
    def _sum_expenses(self) -> Decimal:
        from borrowers.models import ExpenseAnalysis
        total = ExpenseAnalysis.objects.filter(
            loan_application=self.app
        ).aggregate(total=Sum("amount"))["total"]
        return _money(total)

    def _existing_exposure(self):
        """Sum monthly installments of the borrower's other active loans."""
        from loans.models import Loan
        qs = Loan.objects.filter(borrower=self.borrower, outstanding_balance__gt=0)
        total_installments = qs.aggregate(total=Sum("monthly_installment"))["total"]
        return _money(total_installments), qs.count()

    @staticmethod
    def _pct(part: Decimal, whole: Decimal) -> Decimal:
        if whole <= 0:
            return Decimal("0.00")
        return (part / whole * Decimal("100")).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    @staticmethod
    def _classify(iti, dti, disposable_after, income) -> str:
        P = AFFORDABILITY_POLICY
        # Hard fails first
        if disposable_after < 0 or iti > P.ITI_TIGHT or dti > P.DTI_CEILING:
            return "unaffordable"
        # Tight band
        buffer_pct = (disposable_after / income * Decimal("100")) if income > 0 else Decimal("0")
        if iti > P.ITI_COMFORTABLE or buffer_pct < P.BUFFER_MIN:
            return "tight"
        return "comfortable"

    def _recommend(self, outcome, income, disposable_before,
                existing_commitments, installment):
        """
        Produce recommended_max_loan, recommended_term, and plain advice.
        Only meaningful when the current choice isn't comfortable.
        """
        P = AFFORDABILITY_POLICY
        advice = []

        if outcome == "comfortable":
            advice.append("This loan fits comfortably within your budget.")
            return None, None, advice

        # Room available for a repayment at the comfortable threshold, capped
        # by what's actually left after existing commitments.
        comfortable_installment = min(
            income * P.TARGET_ITI / Decimal("100"),
            disposable_before,  # never recommend beyond real disposable income
        )
        comfortable_installment = max(comfortable_installment, Decimal("0")).quantize(TWO_DP)

        # The lender's allowed term range, sorted.
        terms = self._sorted_terms()
        term_min = terms[0] if terms else None
        term_max = terms[-1] if terms else None

        # 1) Recommended MAX AMOUNT at the borrower's chosen term
        rec_max = self._max_amount_for_installment(
            target_installment=comfortable_installment, term=self.app.loan_term
        )

        # 2) Recommended TERM: shortest allowed term that makes the CURRENT
        #    requested amount comfortable. None means no term in range works.
        rec_term = self._min_term_for_amount(
            amount=self.app.loan_amount, target_installment=comfortable_installment
        )

        # 3) Plain-language advice
        if comfortable_installment <= 0:
            # No room at all — existing obligations consume the income.
            advice.append(
                "Your income is already committed to existing expenses and loans, "
                "so there isn't room for a new repayment with this lender right now."
            )
            advice.append(
                "You could apply to another lender from the home page whose terms "
                "may suit you better."
            )
            self._needs_other_lender = True
            return rec_max, None, advice

        # Amount-based suggestion (works within the current term).
        if rec_max and rec_max > 0:
            advice.append(
                f"At a {self.app.loan_term}-month term, a loan up to about "
                f"M{rec_max:,.2f} would keep your repayments comfortable."
            )

        # Term-based suggestion — always framed against the lender's real range.
        if rec_term:
            # A longer term within this lender's range fixes it.
            advice.append(
                f"{self.lender.company_name} offers terms from {term_min} to "
                f"{term_max} months. For the amount you asked for, choosing "
                f"{rec_term} months or longer brings the repayment into a "
                f"comfortable range."
            )
        elif term_max:
            # Even the lender's longest term isn't enough for this amount.
            advice.append(
                f"Even {self.lender.company_name}'s longest term "
                f"({term_max} months) doesn't bring this amount within comfortable "
                f"reach. Consider a smaller amount"
                + (f" (up to about M{rec_max:,.2f})" if rec_max and rec_max > 0 else "")
                + ", or apply to another lender from the home page whose terms may "
                f"suit you better."
            )
            self._needs_other_lender = True

        if outcome == "unaffordable":
            advice.insert(0, "This loan would stretch your budget beyond a safe level.")
        else:  # tight
            advice.insert(0, "This loan is affordable but leaves little breathing room.")

        return rec_max, rec_term, advice

    # ---- reverse-math, matching the flat-interest calculator ---------
    def _max_amount_for_installment(self, target_installment: Decimal, term: int):
        """
        Invert:  installment = amount * (1 + r/100) / term
            =>  amount = installment * term / (1 + r/100)
        Uses the PRODUCT rate when a product is chosen, else the profile rate.
        """
        r = effective_rate(self.product, self.lender)          # ← was self.lender.interest_rate
        factor = Decimal("1") + (r / Decimal("100"))
        if factor <= 0 or not term:
            return None
        amount = (target_installment * Decimal(term)) / factor
        return max(amount, Decimal("0")).quantize(TWO_DP)
    
    
    # ── 3. Replace _min_term_for_amount ────────────────────────────────────────
    def _min_term_for_amount(self, amount, target_installment: Decimal):
        """
        Smallest allowed term whose installment for `amount` is at or below
        target_installment. Uses the PRODUCT rate + the PRODUCT's term range.
        """
        if not amount or target_installment <= 0:
            return None
        r = effective_rate(self.product, self.lender)          # ← was self.lender.interest_rate
        total = Decimal(amount) * (Decimal("1") + r / Decimal("100"))
        for t in self._sorted_terms():
            if (total / Decimal(t)) <= target_installment:
                return t
        return None
    
    
    # ── 4. Replace _sorted_terms ───────────────────────────────────────────────
    def _sorted_terms(self):
        """
        The allowed loan terms as a sorted list of ints — the PRODUCT's term range
        when a product is chosen, else the lender's profile loan_terms.
    
        NOTE: a single_month_end product returns [] (no month term). The advisor's
        instalment math doesn't apply to those; see the guard note below.
        """
        try:
            return sorted(int(t) for t in effective_terms(self.product, self.lender) if int(t) > 0)
        except (TypeError, ValueError):
            return []

    

    def _not_assessable(self, income, expenses, installment,
                        existing_commitments, active_loans) -> dict:
        return {
            "income": income, "expenses": expenses,
            "existing_monthly_commitments": existing_commitments,
            "existing_active_loans": active_loans,
            "installment": installment,
            "disposable_before": income - expenses - existing_commitments,
            "disposable_after": income - expenses - existing_commitments - installment,
            "installment_to_income": Decimal("0.00"),
            "debt_to_income_ratio": Decimal("0.00"),
            "affordability_index_after": Decimal("0.00"),
            "outcome": "unaffordable",
            "recommended_max_loan": None,
            "recommended_term": None,
            "advice": [
                "We couldn't assess affordability because no monthly income is on "
                "your profile. Please add your income before applying.",
            ],
            "needs_other_lender": False,
            "lender_terms": self._sorted_terms(),
            "assessable": False,
        }

SINGLE_COMFORTABLE_FRACTION = Decimal("0.60") 

def _build_single_repayment(self) -> dict:
    """Affordability for a month-end single-repayment product."""
    from loans.loan_terms_resolver import effective_rate  # (adjust path)
 
    income = _money(getattr(self.borrower, "income", 0))
    expenses = self._sum_expenses()
    existing_commitments, active_loans = self._existing_exposure()
 
    # Not assessable without income (same guard as instalment path).
    if income <= 0:
        base = self._not_assessable(
            income, expenses, Decimal("0.00"),
            existing_commitments, active_loans)
        base["repayment_structure"] = "single_month_end"
        return base
 
    disposable_before = income - expenses - existing_commitments
 
    # The single lump the borrower must repay at month-end.
    amount = _money(self.app.loan_amount)
    fee_rate = effective_rate(self.product, self.lender)   # flat monthly fee %
    fee = _money(amount * fee_rate / Decimal("100"))
    total_repayable = _money(amount + fee)
 
    # Disposable AFTER clearing the lump this month.
    disposable_after = disposable_before - total_repayable
 
    # Classify against the month's room, not an installment.
    if total_repayable > disposable_before:
        outcome = "unaffordable"
    elif total_repayable > (disposable_before * SINGLE_COMFORTABLE_FRACTION):
        outcome = "tight"
    else:
        outcome = "comfortable"
 
    # Recommended max amount: the amount whose TOTAL (incl. fee) sits at the
    # comfortable fraction of disposable. Invert total = amount*(1+fee/100):
    #   amount = (disposable * fraction) / (1 + fee_rate/100)
    rec_max = None
    advice = []
    if outcome == "comfortable":
        advice.append(
            f"This is a single repayment of M{total_repayable:,.2f} "
            f"(M{amount:,.2f} plus a M{fee:,.2f} fee), due at month-end. "
            f"It fits comfortably within this month's budget.")
    else:
        factor = Decimal("1") + fee_rate / Decimal("100")
        if factor > 0 and disposable_before > 0:
            rec_max = _money(
                (disposable_before * SINGLE_COMFORTABLE_FRACTION) / factor)
            rec_max = max(rec_max, Decimal("0"))
 
        if outcome == "unaffordable":
            advice.append(
                f"This loan needs a single repayment of M{total_repayable:,.2f} "
                f"at month-end, which is more than your available budget this "
                f"month (M{disposable_before:,.2f}).")
        else:  # tight
            advice.append(
                f"This loan needs a single repayment of M{total_repayable:,.2f} "
                f"at month-end. It's within reach but would use most of this "
                f"month's available budget.")
 
        if rec_max and rec_max > 0:
            advice.append(
                f"A loan up to about M{rec_max:,.2f} would keep the month-end "
                f"repayment comfortable.")
        else:
            advice.append(
                "There isn't room for a month-end repayment this month. You "
                "could apply to another lender from the home page.")
            self._needs_other_lender = True
 
    return {
        "income": income,
        "expenses": expenses,
        "existing_monthly_commitments": existing_commitments,
        "existing_active_loans": active_loans,
        # No monthly installment for a single-repayment loan.
        "installment": Decimal("0.00"),
        "disposable_before": disposable_before,
        "disposable_after": disposable_after,
        # Instalment-only ratios don't apply — zeroed, not faked.
        "installment_to_income": Decimal("0.00"),
        "debt_to_income_ratio": self._pct(existing_commitments, income),
        "affordability_index_after": self._pct(disposable_after, income),
        "outcome": outcome,
        "recommended_max_loan": rec_max,
        "recommended_term": None,          # no term to recommend
        "advice": advice,
        "needs_other_lender": self._needs_other_lender,
        "lender_terms": [],                # month-end has no term list
        "assessable": True,
        # So template/snapshot can tell which model produced this.
        "repayment_structure": "single_month_end",
        "single_repayment_total": total_repayable,
        "single_repayment_fee": fee,
    }