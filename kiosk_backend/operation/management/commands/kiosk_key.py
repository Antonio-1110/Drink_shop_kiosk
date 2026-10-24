from django.core.management.base import BaseCommand, CommandError

from operation.kiosk_auth import new_key
from operation.models import Kiosk


class Command(BaseCommand):
    help = ("Make a new secret key for a kiosk's edge service and print it. The kiosk's old key "
            "stops working. The key is only shown now, so put it in the edge service's settings.")

    def add_arguments(self, parser):
        parser.add_argument('machine_id')

    def handle(self, machine_id, **options):
        try:
            kiosk = Kiosk.objects.get(machine_id=machine_id)
        except Kiosk.DoesNotExist:
            raise CommandError(f"No kiosk with machine ID {machine_id!r}.") from None
        key = new_key(kiosk)
        self.stdout.write(f"New key for {machine_id} ({kiosk.shop}):\n{key}")
