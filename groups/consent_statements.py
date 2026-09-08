"""
Fedha-Grow — consent statement text (versioned)
===============================================
The actual consent language a person agrees to, keyed by version. Versioning
means a stored DataProcessingConsent record always resolves to the EXACT text
that person agreed to, even after the statement is later updated.

╔════════════════════════════════════════════════════════════════════════╗
║  LEGAL REVIEW REQUIRED.                                                 ║
║  This is a DRAFTED, DPA-informed starting point — NOT legal advice and  ║
║  NOT ready for production as-is. A qualified data-protection lawyer in  ║
║  Lesotho MUST review and adjust this wording before it is used to       ║
║  collect real consent. Getting consent language wrong has legal         ║
║  consequences. Treat the text below as a scaffold for that review.      ║
╚════════════════════════════════════════════════════════════════════════╝

To publish a new version: add a new key to CONSENT_STATEMENTS, set
CURRENT_VERSION to it. Never edit an existing version's text once it has been
agreed to by anyone — add a new version instead, so historical records stay true.
"""

CURRENT_VERSION = "2026-09-draft"

CONSENT_STATEMENTS = {
    "2026-09-draft": {
        "title": "Consent to the Collection and Processing of Personal Information",
        "effective": "Draft — pending legal review",
        "body": """
Fedha-Grow (Pty) Ltd ("Fedha-Grow") is a digital platform that connects you to
licensed lending institutions and helps you and your group manage savings and
loans. To do this, we need to collect and process certain personal information
about you. This form explains what we collect, why, and your rights, and asks
for your consent — as required by the Data Protection Act, 2011.

1. WHAT WE COLLECT
   We collect information you (or an authorised agent helping you register)
   provide, which may include: your name, contact details, identity number,
   date of birth, address, employment and income information, your loan
   applications and repayments, and — if you are in a group — your group
   membership and contribution record.

2. WHY WE COLLECT IT (PURPOSE)
   We use this information only to:
     • assess whether a loan is affordable for you, to help prevent
       over-indebtedness;
     • connect your application to licensed lenders you choose to apply to;
     • record and reconcile your savings, contributions and repayments;
     • operate your group's shared record, where you are a group member;
     • communicate with you about your applications and account.
   We do not use your information for any other purpose without your consent.

3. WHO WE SHARE IT WITH
   • Licensed lenders you apply to — only the information needed to assess and
     process your application, and only when you apply to them.
   • Your group — where you are a member, your contribution record is visible
     to your group as part of the group's shared, transparent ledger.
   We do not sell your information. Fedha-Grow does not hold your money; funds
   move between you and your lender or group directly.

4. ASSISTED REGISTRATION
   If an agent or group representative is helping you register, they may capture
   this information on your behalf from a form you have completed. You will set
   your own username and password to secure your account, and you can review and
   correct your information at any time.

5. YOUR RIGHTS
   You have the right to:
     • see the information we hold about you;
     • correct information that is wrong;
     • ask us to stop processing your information, and to WITHDRAW this consent,
       at any time (this may affect our ability to provide the service);
     • ask questions about how your information is handled.

6. SECURITY
   We protect your information with appropriate security measures and process
   it within Lesotho where possible. We keep it only as long as needed for the
   purposes above or as the law requires.

7. YOUR CONSENT
   By signing (or agreeing to) this form, you confirm that you have read and
   understood the above, and you consent to Fedha-Grow collecting and
   processing your personal information as described.
""".strip(),
        "declaration": (
            "I have read and understood this form. I consent to Fedha-Grow "
            "collecting and processing my personal information for the purposes "
            "described above. I understand I may withdraw this consent at any time."
        ),
    },
}


def get_statement(version: str = None) -> dict:
    """Return a consent statement by version (defaults to current)."""
    version = version or CURRENT_VERSION
    return CONSENT_STATEMENTS.get(version, CONSENT_STATEMENTS[CURRENT_VERSION])