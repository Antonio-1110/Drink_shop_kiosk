from django.core.management.base import BaseCommand

from operation.alerts import sync_alerts
from operation.recovery import recover


class Command(BaseCommand):
    help = ("Put things right without staff: fail drinks stuck being made, refund failed drinks and paid "
            "orders a closed shop can't make, retry refunds, then open/clear staff alerts and email them.")

    def handle(self, *args, **options):
        done = recover()
        opened, reminded, resolved = sync_alerts()
        if options['verbosity']:
            self.stdout.write(f"{done}; alerts: {len(opened)} opened, {len(reminded)} reminded, "
                              f"{len(resolved)} resolved.")
