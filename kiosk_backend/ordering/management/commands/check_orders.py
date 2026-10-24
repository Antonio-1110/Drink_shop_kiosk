from django.core.management.base import BaseCommand

from checkout.audit import check_orders, email_staff, report


class Command(BaseCommand):
    help = ("Check that orders, stock and payments add up, and list each broken rule with the order "
            "IDs. Changes nothing. With --email, also emails STAFF_ALERT_EMAILS when anything is found.")

    def add_arguments(self, parser):
        parser.add_argument('--email', action='store_true', help="Email staff if anything is found.")

    def handle(self, *args, email=False, **options):
        broken = check_orders()
        self.stdout.write(report(broken))
        if broken and email and not email_staff(broken):
            self.stderr.write("Nobody to email: set STAFF_ALERT_EMAILS.")
