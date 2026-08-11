"""
Fedha-Grow — USSD menu engine
=============================
A small state machine that turns a caller's keypresses into menu screens.

Channel-agnostic by design: this engine takes the caller's latest input and the
session, and returns a UssdReply(text, end). The HTTP view (views.py) adapts the
specific MNO/aggregator request+response format around it. That means the SAME
menu logic works whether the gateway is Africa's Talking, a direct operator
integration, or a test harness.

REPLY PROTOCOL (universal USSD convention):
  - CON <text>  -> show text, keep session open, expect more input
  - END <text>  -> show text, close session
We return that distinction as UssdReply.end (True/False); the view formats it.

DESIGN NOTES
  - USSD is text-only and session-limited: no document upload here. The menu
    covers what feature-phone users genuinely need; richer actions defer to the
    app or a follow-up SMS link.
  - Borrower-facing only. Nothing here makes a lending decision — it surfaces
    the affordability advice and routes an application to a licensed lender,
    consistent with the facilitation-layer model.
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass
class UssdReply:
    text: str
    end: bool = False


# ---- small helpers -------------------------------------------------
def _menu(title: str, options: list[str], footer: str = "") -> str:
    body = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(options))
    parts = [title, body]
    if footer:
        parts.append(footer)
    return "\n".join(parts)


def _con(text: str) -> UssdReply:
    return UssdReply(text=text, end=False)


def _end(text: str) -> UssdReply:
    return UssdReply(text=text, end=True)


# =====================================================================
# The engine
# =====================================================================
class UssdMenuEngine:
    """
    handle(session, text) -> UssdReply

    `text` is the caller's latest input (the last segment the gateway sends).
    `session` is a UssdSession (or any object with .state, .context, set_state,
    remember, end) — kept duck-typed so it's testable without Django.
    """

    def __init__(self, *, borrower_lookup=None, lender_lookup=None):
        # Injected callables so the engine has no hard Django import and is
        # unit-testable. In production the view passes real ones.
        #   borrower_lookup(phone) -> borrower-or-None
        #   lender_lookup() -> iterable of (id, name) for participating lenders
        self.borrower_lookup = borrower_lookup or (lambda phone: None)
        self.lender_lookup = lender_lookup or (lambda: [])

    def handle(self, session, text: str) -> UssdReply:
        text = (text or "").strip()
        state = session.state

        # Global: blank first request opens the home menu.
        if state == "home":
            return self._home(session)

        handler = getattr(self, f"_state_{state}", None)
        if handler is None:
            session.set_state("home")
            return self._home(session)
        return handler(session, text)

    # ---- home ------------------------------------------------------
    def _home(self, session) -> UssdReply:
        session.set_state("home_choice")
        return _con(_menu(
            "Fedha-Grow",
            ["Check what I can afford", "Apply for a loan",
             "Check application status", "Check my balance"],
        ))

    def _state_home_choice(self, session, text) -> UssdReply:
        if text == "1":
            session.set_state("afford_income")
            return _con("Affordability check\nEnter your monthly income (M):")
        if text == "2":
            return self._begin_apply(session)
        if text == "3":
            return self._status(session)
        if text == "4":
            return self._balance(session)
        return self._invalid(session)

    # ---- affordability (advice, not a decision) --------------------
    def _state_afford_income(self, session, text) -> UssdReply:
        income = _to_decimal(text)
        if income is None or income <= 0:
            return _con("Please enter a valid monthly income (M):")
        session.remember(income=str(income))
        session.set_state("afford_expenses")
        return _con("Enter your total monthly expenses (M):")

    def _state_afford_expenses(self, session, text) -> UssdReply:
        expenses = _to_decimal(text)
        if expenses is None or expenses < 0:
            return _con("Please enter valid monthly expenses (M):")
        income = Decimal(session.context.get("income", "0"))
        disposable = income - expenses

        if disposable <= 0:
            return _end(
                "Based on what you entered, your income is fully used by "
                "expenses. A new loan isn't advisable right now."
            )
        # 30% of income is our comfortable repayment guide (matches the app engine).
        comfortable = (income * Decimal("30") / Decimal("100")).quantize(Decimal("1"))
        comfortable = min(comfortable, disposable)
        return _end(
            f"You have about M{disposable:.0f} left after expenses.\n"
            f"A comfortable monthly repayment would be up to ~M{comfortable:.0f}.\n"
            f"Dial again and choose Apply to continue."
        )

    # ---- apply -----------------------------------------------------
    def _begin_apply(self, session) -> UssdReply:
        lenders = list(self.lender_lookup())
        if not lenders:
            return _end("No participating lenders are available right now. "
                        "Please try again later.")
        # store id<->index mapping for this session
        session.remember(lenders={str(i + 1): {"id": lid, "name": name}
                                  for i, (lid, name) in enumerate(lenders)})
        session.set_state("apply_lender")
        options = [name for (_lid, name) in lenders]
        return _con(_menu("Choose a lender:", options))

    def _state_apply_lender(self, session, text) -> UssdReply:
        lenders = session.context.get("lenders", {})
        chosen = lenders.get(text)
        if not chosen:
            return self._invalid(session)
        session.remember(chosen_lender=chosen)
        session.set_state("apply_amount")
        return _con(f"{chosen['name']}\nEnter the loan amount you want (M):")

    def _state_apply_amount(self, session, text) -> UssdReply:
        amount = _to_decimal(text)
        if amount is None or amount <= 0:
            return _con("Please enter a valid loan amount (M):")
        session.remember(amount=str(amount))
        session.set_state("apply_term")
        return _con("Enter the loan term in months:")

    def _state_apply_term(self, session, text) -> UssdReply:
        try:
            term = int(text)
            if term <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return _con("Please enter a valid number of months:")
        session.remember(term=str(term))
        session.set_state("apply_confirm")
        amount = session.context.get("amount")
        lender = session.context.get("chosen_lender", {}).get("name", "the lender")
        return _con(_menu(
            f"Confirm: M{amount} over {term} month(s) from {lender}",
            ["Confirm", "Cancel"],
        ))

    def _state_apply_confirm(self, session, text) -> UssdReply:
        if text == "1":
            # Handing off to the application pipeline happens in the view layer,
            # which has DB access; the engine just signals intent + a reference.
            session.set_state("done")
            ref = _short_ref(session)
            session.remember(application_ref=ref, submit=True)
            return _end(
                f"Application started (ref {ref}). "
                f"You'll get an SMS with the next steps and any documents needed."
            )
        if text == "2":
            return _end("Application cancelled. Dial again anytime.")
        return self._invalid(session)

    # ---- status & balance (read-only) ------------------------------
    def _status(self, session) -> UssdReply:
        borrower = self.borrower_lookup(session.phone_number)
        if not borrower:
            return _end("We couldn't find an account for this number. "
                        "Please register on the Fedha-Grow app first.")
        # The view injects a richer status; here we keep the engine generic.
        status = session.context.get("latest_status")
        if status:
            return _end(f"Your latest application status: {status}.")
        return _end("You have no active applications on record.")

    def _balance(self, session) -> UssdReply:
        borrower = self.borrower_lookup(session.phone_number)
        if not borrower:
            return _end("We couldn't find an account for this number.")
        balance = session.context.get("outstanding_balance")
        if balance is None:
            return _end("You have no outstanding balance on record.")
        return _end(f"Your outstanding balance is M{balance}.")

    # ---- shared ----------------------------------------------------
    def _invalid(self, session) -> UssdReply:
        return _con("Invalid choice. Please try again:")


# ---- module helpers ------------------------------------------------
def _to_decimal(text: str):
    try:
        return Decimal(str(text).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _short_ref(session) -> str:
    # deterministic-ish short reference from the session id
    sid = getattr(session, "session_id", "") or ""
    tail = sid[-6:].upper() if sid else "FG0000"
    return f"FG{tail}"