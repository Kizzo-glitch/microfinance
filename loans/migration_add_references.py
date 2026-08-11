# loans/migrations/00XX_add_reference_numbers.py
#
# Adds a unique public reference to LoanApplication and Loan, and backfills
# existing rows so the "every transaction has a reference" guarantee holds
# retroactively — not just for new records.
#
# Rename 00XX and set `dependencies` to your latest loans migration before running.
# (Run `python manage.py makemigrations loans --empty` to get a correctly
#  numbered skeleton, then paste these operations in — or let makemigrations
#  create the AddField and add only the RunPython backfill below.)

from django.db import migrations, models


def backfill_references(apps, schema_editor):
    """Give every existing application and loan a unique reference."""
    from loans.references import generate_reference

    LoanApplication = apps.get_model("loans", "LoanApplication")
    Loan = apps.get_model("loans", "Loan")

    for app_obj in LoanApplication.objects.filter(reference_number__isnull=True):
        app_obj.reference_number = generate_reference(
            LoanApplication, "reference_number", prefix="FG"
        )
        app_obj.save(update_fields=["reference_number"])

    for loan_obj in Loan.objects.filter(reference_number__isnull=True):
        loan_obj.reference_number = generate_reference(
            Loan, "reference_number", prefix="FGL"
        )
        loan_obj.save(update_fields=["reference_number"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
         ("loans", "0007_auto_20260811_0827"),  
    ]

    operations = [
        migrations.AddField(
            model_name="loanapplication",
            name="reference_number",
            field=models.CharField(max_length=20, unique=True, editable=False,
                                   null=True, blank=True),
        ),
        migrations.AddField(
            model_name="loan",
            name="reference_number",
            field=models.CharField(max_length=20, unique=True, editable=False,
                                   null=True, blank=True),
        ),
        migrations.RunPython(backfill_references, noop),
    ]