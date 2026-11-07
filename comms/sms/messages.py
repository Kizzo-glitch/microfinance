"""
Fedha-Grow — SMS message catalogue
==================================
One place that owns every SMS the platform sends: its wording and required
context. Views no longer hand-write message strings — they name a message type
and pass context. Change wording here, once, and it changes everywhere.

Each template is a callable taking a context dict and returning the final text.
Keeping them as small functions (not just format strings) lets a message do
light logic — pluralisation, conditional lines — without leaking into views.
"""

from decimal import Decimal


def _m(amount) -> str:
    """Format a Maloti amount consistently."""
    try:
        return f"M{Decimal(str(amount)):,.2f}"
    except Exception:  # noqa: BLE001
        return f"M{amount}"


# ---- catalogue: message_type -> builder(context) -> str ----
MESSAGES = {
    "loan_submitted": lambda c: (
        f"Hi {c['name']}, your loan application {c['ref']} for {_m(c['amount'])} "
        f"was submitted to {c['lender']}. They'll review it and update you. "
        f"Quote {c['ref']} for any query."
    ),
    "loan_approved": lambda c: (
        f"Hi {c['name']}, good news — application {c['ref']} for {_m(c['amount'])} "
        f"from {c['lender']} has been approved."
    ),
    # Sent after approval once the Key Facts Statement exists. Context carries
    # the KFS reference (not the application ref) and the acknowledgement URL;
    # NO 'amount' key — so it cannot reuse the loan_approved builder above.
    "loan_approved_kfs": lambda c: (
        f"Hi {c['name']}, your loan from {c['lender']} is approved. Please review "
        f"and acknowledge your Key Facts Statement (ref {c['ref']}) before it is "
        f"disbursed."
        + (f" Open {c['url']} to review." if c.get("url") else "")
    ),
    "loan_rejected": lambda c: (
        f"Hi {c['name']}, application {c['ref']} of {_m(c['amount'])} from "
        f"{c['lender']} was not approved. Reasons: {c.get('reasons', 'n/a')}."
    ),
    "loan_pending": lambda c: (
        f"Hi {c['name']}, application {c['ref']} of {_m(c['amount'])} from "
        f"{c['lender']} is pending. Reasons: {c.get('reasons', 'n/a')}."
    ),
    "ussd_application_started": lambda c: (
        f"Hi {c['name']}, your loan application {c['ref']} has been started "
        f"via USSD. Open the Fedha-Grow app to add documents and complete it."
    ),

    # ---- KFS acknowledgement flow ----
    # Trigger 1 -> borrower: statement ready to review. Context: name, amount,
    # lender, ref (KFS reference).
    "kfs_ready": lambda c: (
        f"Hi {c['name']}, your Key Facts Statement for the {_m(c['amount'])} loan "
        f"from {c['lender']} is ready (ref {c.get('ref', '')}). Please review and "
        f"acknowledge it in the app before the loan can be disbursed."
    ),
    # Trigger 2 -> lender: borrower has acknowledged, please confirm. Context:
    # borrower, amount, ref. (No 'name'/'lender' — sent to the lender.)
    "kfs_borrower_acknowledged": lambda c: (
        f"{c['borrower']} has acknowledged the Key Facts Statement for their "
        f"{_m(c['amount'])} loan (ref {c.get('ref', '')}). Please confirm in the "
        f"app to proceed to disbursement."
    ),
    # Trigger 3 -> borrower: both parties done. Context: name, lender, ref.
    # (No 'amount' — so it cannot reuse an amount-bearing builder.)
    "kfs_complete": lambda c: (
        f"Hi {c['name']}, {c['lender']} has confirmed your Key Facts Statement "
        f"(ref {c.get('ref', '')}). Both parties have now acknowledged it and your "
        f"loan can proceed to disbursement."
    ),

    
    "payment_confirmed": lambda c: (
        f"Hi {c['name']}, your payment of {_m(c['amount'])} (ref {c['ref']}) has "
        f"been confirmed by {c['lender']}."
        + (" Your loan is now fully paid." if c.get('fully_paid') else "")
    ),
    "payment_rejected": lambda c: (
        f"Hi {c['name']}, your payment claim of {_m(c['amount'])} (ref {c['ref']}) "
        f"could not be confirmed. {c.get('reason', 'Please check the details')}. "
        f"You can correct and resubmit it in the app."
    ),
    "payment_claimed": lambda c: (
        f"Hi {c['name']}, we've recorded your payment claim of {_m(c['amount'])} "
        f"(ref {c['ref']}). {c['lender']} will confirm once they verify receipt."
    ),

        # ---- group: invitations ----
    "group_invitation": lambda c: (
        f"Hi {c['name']}, you've been invited to join {c['group']} on Fedha-Grow. "
        f"Use code {c['code']} or open {c['url']} to activate your account."
    ),
    "group_invite_withdrawn": lambda c: (
        f"Hi {c['name']}, the invitation to join {c['group']} has been withdrawn. "
        f"Contact {c.get('inviter', 'the group admin')} if you have questions."
    ),

    # ---- group: contributions ----
    "group_contribution_claimed": lambda c: (
        f"Hi {c['name']}, we've recorded your contribution claim of {_m(c['amount'])} "
        f"(ref {c['ref']}) to {c['group']}. The treasurer will confirm receipt."
    ),
    "group_contribution_confirmed": lambda c: (
        f"Hi {c['name']}, your contribution of {_m(c['amount'])} (ref {c['ref']}) to "
        f"{c['group']} has been confirmed. Group pool updated."
    ),
    "group_contribution_rejected": lambda c: (
        f"Hi {c['name']}, your contribution claim of {_m(c['amount'])} (ref {c['ref']}) "
        f"to {c['group']} could not be confirmed. {c.get('reason', 'Please check the details')}. "
        f"You can correct and resubmit it."
    ),

    # ---- group: admin absence / acting admin ----
    "admin_inactivity_warning": lambda c: (
        f"Hi {c['name']}, you've been inactive in {c['group']} for several weeks. "
        f"Log in or appoint an acting admin — after 30 days a sub-admin may step in."
    ),
    "acting_admin_appointed": lambda c: (
        f"Hi {c['name']}, {c['actor']} has become acting admin of {c['group']} due to "
        f"inactivity. Log in to resume your role."
    ),
}


class UnknownMessageType(KeyError):
    pass


def render_message(message_type: str, context: dict) -> str:
    """Render a named message. Raises UnknownMessageType on a bad key."""
    builder = MESSAGES.get(message_type)
    if builder is None:
        raise UnknownMessageType(message_type)
    return builder(context or {})

'''
from decimal import Decimal


def _m(amount) -> str:
    """Format a Maloti amount consistently."""
    try:
        return f"M{Decimal(str(amount)):,.2f}"
    except Exception:  # noqa: BLE001
        return f"M{amount}"


# ---- catalogue: message_type -> builder(context) -> str ----
MESSAGES = {
    "loan_submitted": lambda c: (
        f"Hi {c['name']}, your loan application {c['ref']} for {_m(c['amount'])} "
        f"was submitted to {c['lender']}. They'll review it and update you. "
        f"Quote {c['ref']} for any query."
    ),
    "loan_approved": lambda c: (
        f"Hi {c['name']}, good news — application {c['ref']} for {_m(c['amount'])} "
        f"from {c['lender']} has been approved."
    ),
    "loan_rejected": lambda c: (
        f"Hi {c['name']}, application {c['ref']} of {_m(c['amount'])} from "
        f"{c['lender']} was not approved. Reasons: {c.get('reasons', 'n/a')}."
    ),
    "loan_pending": lambda c: (
        f"Hi {c['name']}, application {c['ref']} of {_m(c['amount'])} from "
        f"{c['lender']} is pending. Reasons: {c.get('reasons', 'n/a')}."
    ),
    "ussd_application_started": lambda c: (
        f"Hi {c['name']}, your loan application {c['ref']} has been started "
        f"via USSD. Open the Fedha-Grow app to add documents and complete it."
    ),

    
    "payment_confirmed": lambda c: (
        f"Hi {c['name']}, your payment of {_m(c['amount'])} (ref {c['ref']}) has "
        f"been confirmed by {c['lender']}."
        + (" Your loan is now fully paid." if c.get('fully_paid') else "")
    ),
    "payment_rejected": lambda c: (
        f"Hi {c['name']}, your payment claim of {_m(c['amount'])} (ref {c['ref']}) "
        f"could not be confirmed. {c.get('reason', 'Please check the details')}. "
        f"You can correct and resubmit it in the app."
    ),
    "payment_claimed": lambda c: (
        f"Hi {c['name']}, we've recorded your payment claim of {_m(c['amount'])} "
        f"(ref {c['ref']}). {c['lender']} will confirm once they verify receipt."
    ),

        # ---- group: invitations ----
    "group_invitation": lambda c: (
        f"Hi {c['name']}, you've been invited to join {c['group']} on Fedha-Grow. "
        f"Use code {c['code']} or open {c['url']} to activate your account."
    ),
    "group_invite_withdrawn": lambda c: (
        f"Hi {c['name']}, the invitation to join {c['group']} has been withdrawn. "
        f"Contact {c.get('inviter', 'the group admin')} if you have questions."
    ),

    # ---- group: contributions ----
    "group_contribution_claimed": lambda c: (
        f"Hi {c['name']}, we've recorded your contribution claim of {_m(c['amount'])} "
        f"(ref {c['ref']}) to {c['group']}. The treasurer will confirm receipt."
    ),
    "group_contribution_confirmed": lambda c: (
        f"Hi {c['name']}, your contribution of {_m(c['amount'])} (ref {c['ref']}) to "
        f"{c['group']} has been confirmed. Group pool updated."
    ),
    "group_contribution_rejected": lambda c: (
        f"Hi {c['name']}, your contribution claim of {_m(c['amount'])} (ref {c['ref']}) "
        f"to {c['group']} could not be confirmed. {c.get('reason', 'Please check the details')}. "
        f"You can correct and resubmit it."
    ),

    # ---- group: admin absence / acting admin ----
    "admin_inactivity_warning": lambda c: (
        f"Hi {c['name']}, you've been inactive in {c['group']} for several weeks. "
        f"Log in or appoint an acting admin — after 30 days a sub-admin may step in."
    ),
    "acting_admin_appointed": lambda c: (
        f"Hi {c['name']}, {c['actor']} has become acting admin of {c['group']} due to "
        f"inactivity. Log in to resume your role."
    ),
}


class UnknownMessageType(KeyError):
    pass


def render_message(message_type: str, context: dict) -> str:
    """Render a named message. Raises UnknownMessageType on a bad key."""
    builder = MESSAGES.get(message_type)
    if builder is None:
        raise UnknownMessageType(message_type)
    return builder(context or {})
'''