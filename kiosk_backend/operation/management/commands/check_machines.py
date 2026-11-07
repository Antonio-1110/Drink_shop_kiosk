from django.core.management.base import BaseCommand

from operation.machine import mark_silent_machines_offline


class Command(BaseCommand):
    help = "Mark machines that stopped checking in as offline (their shops stop taking orders)."

    def handle(self, *args, **options):
        count = mark_silent_machines_offline()
        if options['verbosity']:
            self.stdout.write(f"{count} machine(s) marked offline.")
