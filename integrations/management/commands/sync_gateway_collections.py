"""
Finish instant payments left open: the gateway was unreachable, the borrower
closed the page, or a code expired. Run every few minutes:

    python manage.py sync_gateway_collections
"""
from django.core.management.base import BaseCommand

from integrations.repayments import sync_unfinished


class Command(BaseCommand):
    help = "Refresh unfinished instant payments from the payment gateway."

    def handle(self, *args, **options):
        n = sync_unfinished()
        self.stdout.write(f"checked {n} unfinished payment(s)")
