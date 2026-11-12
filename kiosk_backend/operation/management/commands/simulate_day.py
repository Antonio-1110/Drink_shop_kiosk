"""Run whole days at a pretend shop, with pretend customers and a pretend machine, and report any
order, payment or stock that ends up wrong. See operation/simulation.py.

    python manage.py simulate_day                    # yesterday, default faults, nothing saved
    python manage.py simulate_day --days 3 --seed 7
    python manage.py simulate_day --no-faults --orders-per-hour 30
    python manage.py simulate_day --keep             # keep the shop and its orders (e.g. for the dashboard)

Exits with an error when it finds problems, so it can run in CI.
"""
import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from operation.simulation import DEFAULT_FAULTS, SGT, Scenario, Simulation


def fault(text):
    kind, at, minutes = text.split(',')
    return kind, at, int(minutes)


class Command(BaseCommand):
    help = "Simulate whole days of kiosk and phone orders, payments and machine faults, and check the results."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=1)
        parser.add_argument('--date', help="First day, YYYY-MM-DD (default: the days up to yesterday).")
        parser.add_argument('--opens', default='08:00', help="HH:MM, Singapore time.")
        parser.add_argument('--closes', default='22:00', help="HH:MM, Singapore time.")
        parser.add_argument('--seed', type=int, default=1, help="Same seed, same day.")
        parser.add_argument('--orders-per-hour', type=float, default=12.0, help="Outside the lunch and evening peaks.")
        parser.add_argument('--phone-share', type=float, default=0.3)
        parser.add_argument('--fail-rate', type=float, default=0.03, help="Chance each attempt at a drink fails.")
        parser.add_argument('--stock-factor', type=float, default=3.0,
                            help="Morning stock as a multiple of the demo stock (1 sells out by the afternoon).")
        parser.add_argument('--fault', type=fault, action='append', metavar='KIND,HH:MM,MINUTES',
                            help="warm-fridge, out-of-cups or offline; repeat for more. Replaces the default faults.")
        parser.add_argument('--no-faults', action='store_true')
        parser.add_argument('--keep', action='store_true',
                            help="Save the simulated shop and orders. Development databases only: the background "
                                 "jobs it runs also act on other shops' unpaid orders and machines.")

    def handle(self, *args, **o):
        faults = [] if o['no_faults'] else (o['fault'] or list(DEFAULT_FAULTS))
        start = datetime.strptime(o['date'], '%Y-%m-%d').replace(tzinfo=SGT) if o['date'] else None
        scenario = Scenario(days=o['days'], start=start, seed=o['seed'], orders_per_hour=o['orders_per_hour'],
                            phone_share=o['phone_share'], fail_rate=o['fail_rate'], faults=faults,
                            stock_factor=o['stock_factor'], opens=o['opens'], closes=o['closes'])
        if o['verbosity'] < 2:
            logging.disable(logging.CRITICAL)  # the backend's own warnings; -v 2 shows them
        try:
            with transaction.atomic():
                sim = Simulation(scenario).run()
                if not o['keep']:
                    transaction.set_rollback(True)
        finally:
            logging.disable(logging.NOTSET)
        for day in sim.days:
            self.stdout.write(report_day(day))
        if o['keep']:
            self.stdout.write(f"Kept as \"{sim.shop.name}\" (shop {sim.shop.pk}).")
        if sim.problems:
            self.stdout.write(self.style.ERROR(f"\n{len(sim.problems)} problem(s):"))
            for day, what in sim.problems[:50]:
                self.stdout.write(f"  {day}: {what}")
            if len(sim.problems) > 50:
                self.stdout.write(f"  ...and {len(sim.problems) - 50} more")
            raise CommandError(f"The simulation found {len(sim.problems)} problem(s).")
        self.stdout.write(self.style.SUCCESS("\nNo problems: every order, payment and stock change added up."))


def hhmm(at):
    return f"{timezone.localtime(at, SGT):%H:%M}"


def report_day(day):
    lines = [f"\n{day['day']:%a %d %b %Y}: {day['customers']} customers, {day['orders']} orders "
             f"({day['channels']['kiosk']} kiosk, {day['channels']['phone']} phone), takings ${day['revenue']}"]
    lines.append("  Orders now: " + ", ".join(f"{n} {s.lower()}" for s, n in day['statuses'].most_common()))
    lines.append("  Customers: " + ", ".join(f"{n} {o}" for o, n in day['outcomes'].most_common()))
    for f in day['faults']:
        lines.append(f"  Fault: {f.kind} {hhmm(f.start)}-{hhmm(f.end)}")
    for a, b in day['lock_spans']:
        lines.append(f"  Dairy lock: {hhmm(a)}-{hhmm(b) if b else 'end of day'}")
    if day['low_stock']:
        lines.append("  Nearly out by closing: " + ", ".join(day['low_stock']))
    return "\n".join(lines)
