"""
Correct loans saved with flat interest.

Before the fix, approving a loan (and every later save) set its total to
amount x (1 + annual rate): a full year of flat interest whatever the term.
This recalculates each loan from the lawful source — its Key Facts Statement
if it has one, otherwise the declining-balance calculation — and resets the
outstanding balance to total minus CONFIRMED payments.

    python manage.py correct_loan_totals            # dry run: show changes only
    python manage.py correct_loan_totals --apply    # save the changes
    python manage.py correct_loan_totals --loan 42  # one loan only

Loans whose confirmed payments already exceed the corrected total are listed
as OVERPAID: the borrower may be owed a refund. Those need a human decision.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from loans.models import Loan
from loans.pricing import lawful_total, money


class Command(BaseCommand):
    help = "Recalculate loan totals and balances with the lawful declining-balance method."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Save the corrected figures. Without it, nothing is changed.")
        parser.add_argument("--loan", type=int, help="Only this loan id.")

    def handle(self, *args, **options):
        apply = options["apply"]
        loans = Loan.objects.select_related("product").order_by("id")
        if options["loan"]:
            loans = loans.filter(pk=options["loan"])

        changed, overpaid = 0, 0
        reduction = Decimal("0.00")

        with transaction.atomic():
            for loan in loans:
                new_total, source = lawful_total(loan)
                confirmed = loan.payments.filter(status="confirmed").values_list("amount", flat=True)
                paid = money(sum(confirmed, Decimal("0")))
                new_outstanding = max(new_total - paid, Decimal("0.00"))
                old_total = money(loan.total_repayable or 0)
                old_outstanding = money(loan.outstanding_balance or 0)

                if new_total == old_total and new_outstanding == old_outstanding:
                    continue
                changed += 1
                reduction += old_total - new_total

                line = (f"Loan {loan.id} ({loan.reference_number or '-'}), M{money(loan.amount)} "
                        f"over {loan.loan_term} mo [{source}]: "
                        f"total M{old_total} -> M{new_total}; "
                        f"outstanding M{old_outstanding} -> M{new_outstanding}")
                if paid > new_total:
                    overpaid += 1
                    line += f"  OVERPAID by M{paid - new_total}"
                    self.stdout.write(self.style.WARNING(line))
                else:
                    self.stdout.write(line)

                if apply:
                    Loan.objects.filter(pk=loan.pk).update(
                        total_repayable=new_total, outstanding_balance=new_outstanding)

        verb = "Corrected" if apply else "Would correct"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {changed} loan(s); totals reduced by M{reduction} in all."))
        if overpaid:
            self.stdout.write(self.style.WARNING(
                f"{overpaid} loan(s) are OVERPAID under the lawful figures. "
                f"Their balance is set to 0; decide on refunds with the lender."))
        if changed and not apply:
            self.stdout.write("Dry run only. Re-run with --apply to save.")
