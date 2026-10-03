"""Runs the backend's background jobs, for as long as it's left running:

- every EXPIRE_ORDERS_EVERY_SECONDS (60): cancel unpaid orders whose time ran out (expire_orders)
- once a day at CHECK_ORDERS_AT: check orders, stock and payments add up, emailing staff if not
  (check_orders --email)

Run one of these next to the web server in production. Each job's errors are logged and the
loop carries on.
"""
import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections, reset_queries
from django.utils import timezone

logger = logging.getLogger(__name__)


class Jobs:
    def __init__(self, now):
        self.next_expire = now
        self.next_check = self.daily_after(now)

    @staticmethod
    def daily_after(now):
        """The next CHECK_ORDERS_AT (in TIME_ZONE) strictly after `now`."""
        hour, minute = map(int, settings.CHECK_ORDERS_AT.split(':'))
        local = timezone.localtime(now)
        at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= local:
            at = timezone.make_aware(datetime.combine(at.date() + timedelta(days=1), at.time()))
        return at

    def run_due(self, now):
        """Runs whatever is due at `now`. Returns the names of the jobs it ran."""
        ran = []
        if now >= self.next_expire:
            self.run('expire_orders', verbosity=0)
            self.next_expire = now + timedelta(seconds=settings.EXPIRE_ORDERS_EVERY_SECONDS)
            ran.append('expire_orders')
        if now >= self.next_check:
            self.run('check_orders', '--email')
            self.next_check = self.daily_after(now)
            ran.append('check_orders')
        return ran

    @staticmethod
    def run(*command, **options):
        close_old_connections()  # a long-running process mustn't keep a dropped database connection
        reset_queries()  # with DEBUG on, Django remembers every query until this
        try:
            call_command(*command, **options)
        except Exception:
            logger.exception("Background job %s failed", command[0])


class Command(BaseCommand):
    help = "Run the background jobs (cancel expired unpaid orders every minute, check orders daily) until stopped."

    def handle(self, *args, **options):
        jobs = Jobs(timezone.now())
        self.stdout.write(f"Cancelling expired unpaid orders every {settings.EXPIRE_ORDERS_EVERY_SECONDS}s; "
                          f"next order check at {jobs.next_check:%Y-%m-%d %H:%M %Z}. Ctrl-C stops.")
        while True:
            jobs.run_due(timezone.now())
            time.sleep(1)
