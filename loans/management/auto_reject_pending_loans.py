from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from .models import LoanApplication, Notification


class Command(BaseCommand):
    help = 'Automatically reject loan applications pending for more than 14 days.'

    def handle(self, *args, **kwargs):
        fourteen_days_ago = now() - timedelta(days=14)
        pending_loans = LoanApplication.objects.filter(
            status='pending',
            status_last_updated__lt=fourteen_days_ago
        )

        for loan in pending_loans:
            loan.status = 'rejected'
            loan.rejection_reasons = ['incomplete_docs']  # Automatically apply this reason
            loan.save()

            # Send notification to borrower
            Notification.objects.create(
                user=loan.borrower.user,
                message=f"❌ Your loan application ID {loan.id} was automatically rejected due to incomplete documents after 14 days.",
                category="loan_rejected",
                loan_application=loan
            )

            self.stdout.write(self.style.SUCCESS(f"Loan {loan.id} automatically rejected."))