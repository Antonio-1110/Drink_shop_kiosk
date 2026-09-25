from django.core.management.base import BaseCommand
from ordering.utils import expire_unpaid_orders


class Command(BaseCommand):
    help = "Cancel orders left unpaid past ORDER_PAYMENT_TIMEOUT_MINUTES and return their stock."

    def handle(self, *args, **options):
        count = expire_unpaid_orders()
        self.stdout.write(f"Cancelled {count} unpaid order(s).")
