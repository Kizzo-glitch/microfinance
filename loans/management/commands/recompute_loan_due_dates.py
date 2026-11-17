"""
Recompute due dates for existing loans.

Loans created before the fix had due_date = application date + 365 days,
whatever their term. This recalculates them with Loan.compute_due_date().

    python manage.py recompute_loan_due_dates           # dry run: show changes only
    python manage.py recompute_loan_due_dates --apply   # write the changes
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from loans.models import Loan


class Command(BaseCommand):
    help = "Recompute Loan.due_date from the first payment date and the term."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Save the new dates. Without it, nothing is changed.")

    def handle(self, *args, **options):
        apply = options["apply"]
        changed = 0
        with transaction.atomic():
            for loan in Loan.objects.select_related("product").order_by("id"):
                new = loan.compute_due_date()
                if new == loan.due_date:
                    continue
                changed += 1
                self.stdout.write(
                    f"Loan {loan.id} ({loan.reference_number or '-'}, term {loan.loan_term}): "
                    f"{loan.due_date} -> {new}")
                if apply:
                    Loan.objects.filter(pk=loan.pk).update(due_date=new)
        verb = "Updated" if apply else "Would update"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} loan(s)."))
        if changed and not apply:
            self.stdout.write("Dry run only. Re-run with --apply to save.")
