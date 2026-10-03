from django.core.management.base import BaseCommand
from checkout.services import expire_unpaid_orders


class Command(BaseCommand):
    help = "Cancel orders whose payment time has run out and return their stock."

    def handle(self, *args, **options):
        count = expire_unpaid_orders()
        # run_jobs runs this every minute with verbosity 0, so only say something when it did something
        if count or options['verbosity']:
            self.stdout.write(f"Cancelled {count} unpaid order(s).")
