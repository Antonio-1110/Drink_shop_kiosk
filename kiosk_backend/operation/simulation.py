"""Whole days at a shop, simulated end to end with no hardware (`manage.py simulate_day`).

A pretend machine (the same Machine the `simulate_machine` command uses) and pretend customers use
the real HTTP API in-process, on a simulated clock, so a 14-hour day runs in a few seconds:

- customers at the kiosk and on the phone browse the menu, order menu and designer drinks, pay,
  cancel, walk away, let the kiosk time out, pay late, get notified twice or pay the wrong amount,
  and collect with their PIN or QR code (or never come);
- the machine checks in every minute, sends fridge temperatures, takes paid orders one at a time,
  sometimes fails a drink, and has faults on a timetable (warm fridge, out of cups, offline);
- the background jobs run every minute (cancel unpaid orders, mark silent machines offline);
- "staff" only restock before opening and clear the dairy lock once the fridge is cold again.

While it runs it checks every reply against what should happen (no orders while the shop is closed,
no milk drinks under the dairy lock, collecting only when ready). At the end of each day it checks
what the database says: each order's status against what its customer and the machine did, every
status change against the allowed moves, payments against order totals, and stock against what the
orders used. Anything wrong is listed as a problem.
"""
import io
import itertools
import json
import os
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.db.models import Sum
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from checkout import audit, services
from checkout.models import PaymentAttempt, StockHold
from ordering.models import Order, OrderEvent
from ordering.status import TRANSITIONS
from .kiosk_auth import new_key
from .machine import mark_silent_machines_offline
from .management.commands.simulate_machine import Machine
from .models import DesignerConfig, Drink, Ingredient, Inventory, Kiosk, Shop, StockMovement

S = Order.Status
SGT = ZoneInfo('Asia/Singapore')
_runs = itertools.count(1)
TICK = timedelta(seconds=30)

# how often each kind of customer does what, out of 100
KIOSK_PLANS = {'pay': 76, 'abandon': 6, 'cancel': 5, 'idle': 4, 'late_pay': 3, 'pay_twice': 2,
               'wrong_amount': 2, 'pay_fails_then_pays': 2}
PHONE_PLANS = {'pay': 84, 'abandon': 4, 'cancel': 3, 'late_pay': 2, 'no_show': 4, 'pay_twice': 1,
               'pay_fails_then_pays': 2}

# (fault, start as HH:MM, minutes); the default day has one of each
DEFAULT_FAULTS = [('warm-fridge', '15:00', 15), ('out-of-cups', '17:30', 20), ('offline', '19:30', 8)]


@dataclass
class Fault:
    kind: str
    start: datetime
    end: datetime


@dataclass
class Scenario:
    days: int = 1
    start: datetime | None = None  # first day; default so the last day simulated is yesterday
    opens: str = '08:00'
    closes: str = '22:00'
    orders_per_hour: float = 12.0  # outside the lunch and evening peaks
    phone_share: float = 0.3
    designer_share: float = 0.1
    fail_rate: float = 0.03  # chance each attempt at a drink fails (it's retried once)
    faults: list = field(default_factory=lambda: list(DEFAULT_FAULTS))
    staff_clears_lock_after: int = 45  # minutes after the fridge is cold again
    make_seconds: int = 60  # per drink
    stock_factor: float = 3.0  # the morning restock fills up to the demo stock levels times this
    seed: int = 1


def day_rate(hour):
    """How busy each hour is, as a multiple of orders_per_hour."""
    if 12 <= hour < 14:
        return 2.0
    if 17 <= hour < 19:
        return 1.8
    if hour < 10 or hour >= 20:
        return 0.6
    return 1.0


class Clock:
    def __init__(self, at):
        self.at = at

    def now(self):
        return self.at

    def timestamp(self):
        return self.at.timestamp()


def client_sender(client, key):
    """A send(method, path, body) for Machine that calls the backend in-process with a Django test
    Client, the same calls the HTTP sender makes."""
    def send(method, path, body=None):
        res = client.generic(method, path, json.dumps(body) if body is not None else '',
                             content_type='application/json', HTTP_AUTHORIZATION=f"Kiosk {key}")
        try:
            data = json.loads(res.content) if res.content else None
        except ValueError:
            data = None
        return res.status_code, data
    return send


@dataclass
class Visit:
    """One customer and what they did, so the end-of-day check knows what each order should be."""
    n: int
    channel: str  # kiosk or phone
    plan: str
    arrive: datetime
    step: str = 'browse'
    next_at: datetime | None = None
    cart: list = field(default_factory=list)
    order_id: int | None = None
    token: str = ''
    pin: str = ''
    qr: str = ''
    total: Decimal | None = None
    hold_until: datetime | None = None
    paid: bool = False  # a payment was accepted for the order
    refunds_expected: int = 0  # payments that should have been turned down
    collected: bool = False
    outcome: str = ''
    waited_since: datetime | None = None
    chilled: bool = False  # the order needs a chilled ingredient


class Simulation:
    def __init__(self, scenario):
        self.sc = scenario
        self.rng = random.Random(scenario.seed)
        self.problems = []  # (day, what's wrong)
        self.days = []  # per-day summaries
        # pickup attempts are throttled per address: each run gets its own, so an earlier run's attempts
        # (at the same simulated times) don't count against it
        run = next(_runs)
        self.client = Client(REMOTE_ADDR=f"10.{os.getpid() % 250}.{run // 250 % 250}.{run % 250 + 1}")
        self.visits = []
        self.made = {}  # order id -> READY or FAILED, as the machine reported it

    # --- setup ---

    def setup(self):
        if not Drink.objects.filter(is_active=True, required__isnull=False).exists():
            call_command('seed_demo', verbosity=0, stdout=io.StringIO())
        from .management.commands.seed_demo import CHILLED, INGREDIENTS
        stock_levels = {name: Decimal(stock) for name, _, stock, *_ in INGREDIENTS}
        n = Shop.objects.filter(name__startswith="Simulated shop").count() + 1
        self.shop = Shop.objects.create(name=f"Simulated shop {n}", address="Simulation, Singapore")
        self.kiosk = Kiosk.objects.create(shop=self.shop, machine_id=f"SIM-{self.shop.pk}")
        key = new_key(self.kiosk)
        self.targets = {}
        for ingredient in Ingredient.objects.all():
            other = (Inventory.objects.filter(ingredient=ingredient)
                     .exclude(min_safe_temp_c=None, max_safe_temp_c=None).first())
            chilled = ({'min_safe_temp_c': other.min_safe_temp_c, 'max_safe_temp_c': other.max_safe_temp_c} if other
                       else {'min_safe_temp_c': Decimal('0'), 'max_safe_temp_c': Decimal('4')}
                       if ingredient.name in CHILLED else {})
            inv = Inventory.objects.create(shop=self.shop, ingredient=ingredient, current_stock=0, **chilled)
            self.targets[inv.pk] = (stock_levels.get(ingredient.name, Decimal('5000'))
                                   * Decimal(str(self.sc.stock_factor))).quantize(Decimal('1'))
        self.chilled_ids = set(Inventory.objects.filter(shop=self.shop).exclude(
            min_safe_temp_c=None, max_safe_temp_c=None).values_list('ingredient_id', flat=True))
        self.machine = Machine(client_sender(self.client, key), fail_rate=self.sc.fail_rate,
                               rng=self.rng, sleep=lambda s: None, log=lambda line: None)
        self.opening_stock = {}

    # --- the day ---

    def run(self):
        start = self.sc.start or (timezone.localtime(timezone.now(), SGT) - timedelta(days=self.sc.days))
        start = start.astimezone(SGT).date()
        self.clock = Clock(datetime.combine(start, dtime(6), SGT).astimezone(dt_timezone.utc))
        throttle_timer = staticmethod(self.clock.timestamp)
        payments = settings.PAYMENT_METHODS if 'paynow' in settings.PAYMENT_METHODS else [*settings.PAYMENT_METHODS, 'paynow']
        with mock.patch('django.utils.timezone.now', self.clock.now), \
                mock.patch.object(SimpleRateThrottle, 'timer', throttle_timer), \
                override_settings(MACHINE_SIMULATOR=False, ALLOWED_HOSTS=['testserver'], PAYMENT_METHODS=payments,
                                  PAYNOW_PROXY_VALUE=settings.PAYNOW_PROXY_VALUE or '000000000X'):
            self.setup()
            for d in range(self.sc.days):
                self.run_day(start + timedelta(days=d))
        return self

    def at(self, day, hhmm):
        h, m = map(int, hhmm.split(':'))
        return datetime.combine(day, dtime(h, m), SGT).astimezone(dt_timezone.utc)

    def run_day(self, day):
        self.day = day
        opens, closes = self.at(day, self.sc.opens), self.at(day, self.sc.closes)
        self.opens, self.closes = opens, closes
        self.faults = [Fault(kind, self.at(day, hhmm), self.at(day, hhmm) + timedelta(minutes=mins))
                       for kind, hhmm, mins in self.sc.faults]
        self.clock.at = opens - timedelta(minutes=30)
        first_order = Order.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
        visits_before = len(self.visits)
        self.restock()
        # the machine: cleaning before opening, then open
        self.job = None
        self.job_done_at = None
        self.next_check_in = self.clock.at
        self.next_jobs = self.clock.at
        self.sent_status = None
        self.sent_out_of_cups = False
        self.last_check_in = None
        self.locked = False
        self.lock_clear_at = None
        self.lock_spans = []
        # customers
        arrivals = []
        t = opens - timedelta(minutes=10)
        while t < closes + timedelta(minutes=10):
            rate = self.sc.orders_per_hour * day_rate(timezone.localtime(t, SGT).hour)
            for _ in range(self.poisson(rate * TICK.total_seconds() / 3600)):
                arrivals.append(t + timedelta(seconds=self.rng.uniform(0, TICK.total_seconds())))
            t += TICK
        arrivals.sort()
        pending = []
        end = closes + timedelta(minutes=60)
        while self.clock.at < end or (self.clock.at < closes + timedelta(hours=3) and self.busy(pending)):
            now = self.clock.at
            self.machine_tick(now)
            if now >= self.next_jobs:
                services.expire_unpaid_orders()
                mark_silent_machines_offline()
                self.next_jobs = now + timedelta(seconds=60)
            while arrivals and arrivals[0] <= now:
                pending.append(self.new_visit(arrivals.pop(0)))
            for visit in list(pending):
                if visit.next_at <= now:
                    self.step(visit, now)
                    if visit.step == 'done':
                        pending.remove(visit)
            self.clock.at = now + TICK
        for visit in pending:
            visit.outcome = visit.outcome or 'left at closing'
        # overnight the machine is off; it checks in again (in maintenance) half an hour before opening
        self.end_of_day(first_order, self.visits[visits_before:])

    def busy(self, pending):
        return self.job is not None or Order.objects.filter(shop=self.shop, status=S.PAID).exists() or any(
            v.step in ('wait', 'collect') for v in pending)

    def poisson(self, mean):
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def restock(self):
        """Staff top every ingredient back up before opening (and note what the day starts with)."""
        for inv in Inventory.objects.filter(shop=self.shop):
            gap = self.targets[inv.pk] - inv.current_stock
            if gap > 0:
                inv.adjust_stock(gap, StockMovement.Reason.RESTOCK, note="Simulated morning restock")
        self.opening_stock = dict(Inventory.objects.filter(shop=self.shop).values_list('pk', 'current_stock'))
        self.movements_from = StockMovement.objects.order_by('-pk').values_list('pk', flat=True).first() or 0

    # --- the machine ---

    def fault_now(self, now):
        return next((f.kind for f in self.faults if f.start <= now < f.end), 'none')

    def expect_open(self, now):
        """Whether the shop should take orders now, from what the machine last told the backend.
        None right at the check-in timeout, where a second either way is fine."""
        if self.sent_status != 'ONLINE' or self.last_check_in is None or self.sent_out_of_cups:
            return False
        silent = (now - self.last_check_in).total_seconds()
        timeout = settings.MACHINE_HEARTBEAT_TIMEOUT_SECONDS
        if abs(silent - timeout) <= 1:
            return None
        return silent < timeout

    def machine_tick(self, now):
        fault = self.fault_now(now)
        self.machine.fault = fault
        if now >= self.next_check_in:
            self.next_check_in = now + timedelta(seconds=60)
            status = 'ONLINE' if self.opens <= now < self.closes else 'MAINTENANCE'
            if self.machine.check_in(status) is not None:
                self.sent_status, self.last_check_in = status, now
                self.sent_out_of_cups = fault == 'out-of-cups'
            reply = self.machine.send_temperatures()
            if reply is not None:
                if fault == 'warm-fridge' and not self.locked:
                    self.locked = True
                    self.lock_spans.append([now, None])
                if not reply['sfa_locked'] and fault == 'warm-fridge':
                    self.problem(f"A warm fridge reading at {self.hhmm(now)} didn't turn on the dairy lock")
            if self.locked and fault != 'warm-fridge' and self.lock_clear_at is None:
                self.lock_clear_at = now + timedelta(minutes=self.sc.staff_clears_lock_after)
        if self.locked and self.lock_clear_at and now >= self.lock_clear_at:
            # staff check the fridge and clear the lock in the admin
            Kiosk.objects.filter(pk=self.kiosk.pk).update(sfa_locked=False, sfa_lock_reason='')
            self.locked, self.lock_clear_at = False, None
            self.lock_spans[-1][1] = now
        if fault == 'offline':
            return  # can't take or report anything; a drink in progress is finished and reported later
        if self.job is not None and now >= self.job_done_at:
            to, code = self.machine.report(self.job, self.job_problem)
            if code != 200:
                self.problem(f"Order {self.job['id']}: the machine's {to} report was refused ({code})")
            self.made[self.job['id']] = to
            self.job = None
        if self.job is None:
            job = self.machine.take_next()
            if job is not None and self.sent_out_of_cups:
                self.problem(f"Order {job['id']}: the machine was given an order while it reported it was out of cups")
            if job is not None:
                # whether it works is settled now: once a drink has its cup, running out doesn't stop it
                self.job, self.job_problem = job, self.machine.make(job)
                drinks = len(job['items'])
                self.job_done_at = now + timedelta(seconds=self.sc.make_seconds * drinks)
                lines = {line['ingredient'] for item in job['items'] for line in item['lines']}
                if self.locked and lines & self.chilled_ids:
                    self.problem(f"Order {job['id']}: the machine was given a drink with chilled "
                                 f"ingredients under the dairy lock")

    # --- customers ---

    def new_visit(self, at):
        channel = 'phone' if self.rng.random() < self.sc.phone_share else 'kiosk'
        plans = PHONE_PLANS if channel == 'phone' else KIOSK_PLANS
        plan = self.rng.choices(list(plans), weights=list(plans.values()))[0]
        visit = Visit(n=len(self.visits) + 1, channel=channel, plan=plan, arrive=at, next_at=at)
        self.visits.append(visit)
        return visit

    def api(self, method, path, body=None, **params):
        if method == 'GET':
            res = self.client.get(path, params)
        else:
            res = self.client.post(path, json.dumps(body or {}), content_type='application/json')
        try:
            data = json.loads(res.content) if res.content else None
        except ValueError:
            data = None
        return res.status_code, data

    def later(self, visit, step, seconds):
        visit.step, visit.next_at = step, self.clock.at + timedelta(seconds=seconds)

    def leave(self, visit, outcome):
        visit.step, visit.outcome = 'done', outcome

    def step(self, visit, now):
        getattr(self, f"on_{visit.step}")(visit, now)

    def on_browse(self, visit, now):
        code, menu = self.api('GET', '/ordering/drinks/', shop_id=self.shop.pk)
        open_ = self.expect_open(now)
        if code != 200:
            self.problem(f"The menu failed at {self.hhmm(now)}: {code}")
            return self.leave(visit, 'menu failed')
        if open_ is False and menu:
            self.problem(f"The menu listed drinks at {self.hhmm(now)} while the shop was closed")
        if self.locked:
            chilled = {d['id'] for d in menu} & self.chilled_drinks()
            if chilled:
                self.problem(f"The menu listed milk drinks {sorted(chilled)} at {self.hhmm(now)} under the dairy lock")
        if open_:
            self.check_menu({d['id'] for d in menu}, now)
        cart = []
        if self.rng.random() < self.sc.designer_share:
            code, options = self.api('GET', '/ordering/designer/options/', shop_id=self.shop.pk)
            liquids = [i['code'] for i in options['ingredients'] if i['available'] and i['kind'] == 'liquid']
            toppings = [i['code'] for i in options['ingredients'] if i['available'] and i['kind'] == 'topping']
            if liquids:
                custom = self.rng.sample(liquids, min(len(liquids), self.rng.choice([1, 2])))
                if toppings and self.rng.random() < 0.5:
                    custom.append(self.rng.choice(toppings))
                cart.append({'custom': custom, **self.options()})
        if menu:
            for _ in range(self.rng.choices([1, 2, 3], weights=[70, 22, 8])[0] - len(cart)):
                cart.append({'drink': self.rng.choice(menu)['id'], **self.options()})
        if not cart:
            return self.leave(visit, 'closed' if not open_ else 'nothing to buy')
        visit.cart = cart
        self.later(visit, 'place', self.rng.uniform(20, 90))

    def check_menu(self, listed, now):
        """The menu should list exactly the drinks there's stock for (a small cup), apart from the
        dairy lock."""
        stock = dict(Inventory.objects.filter(shop=self.shop).values_list('ingredient_id', 'current_stock'))
        makeable = set()
        for drink in Drink.objects.filter(is_active=True).prefetch_related('required'):
            lines = list(drink.required.all())
            if all(stock.get(line.ingredient_id, 0) >= line.required_quantity for line in lines) and not (
                    self.locked and {line.ingredient_id for line in lines} & self.chilled_ids):
                makeable.add(drink.pk)
        for drink_id in sorted(makeable - listed):
            self.problem(f"The menu at {self.hhmm(now)} hid {Drink.objects.get(pk=drink_id).name}, "
                         f"which there was stock for")
        for drink_id in sorted(listed - makeable):
            self.problem(f"The menu at {self.hhmm(now)} listed {Drink.objects.get(pk=drink_id).name}, "
                         f"which there wasn't stock for")

    def options(self):
        return {'size': self.rng.choice([0, 0, 1]), 'sugar': self.rng.choice([0, 1, 2, 3, 4, 4]),
                'ice': self.rng.choice([0, 2, 4, 4])}

    def chilled_drinks(self):
        return set(Drink.objects.filter(required__ingredient_id__in=self.chilled_ids).values_list('pk', flat=True))

    def needs_chilled(self, order_id):
        from checkout.services import order_needs
        return bool(set(order_needs(Order.objects.get(pk=order_id))) & self.chilled_ids)

    def on_place(self, visit, now, retried=False):
        body = {'shop': self.shop.pk, 'items': visit.cart}
        if visit.channel == 'phone':
            body['user_id'] = f"app:sim-{visit.n}"
        code, data = self.api('POST', '/ordering/log-order/', body)
        open_ = self.expect_open(now)
        if code == 503:
            if open_:
                self.problem(f"An order at {self.hhmm(now)} was refused as closed while the machine was online")
            return self.leave(visit, 'closed')
        if open_ is False and code != 503:
            self.problem(f"An order at {self.hhmm(now)} got {code} while the shop should have been closed")
        if code == 409:
            unavailable = set(data.get('drinks', []))
            keep = [item for item in visit.cart if item.get('drink') and item['drink'] not in unavailable]
            if not retried and keep and len(keep) < len(visit.cart):
                visit.cart = keep
                return self.on_place(visit, now, retried=True)
            return self.leave(visit, 'sold out')
        if code != 201:
            self.problem(f"Placing an order at {self.hhmm(now)} failed: {code} {data}")
            return self.leave(visit, 'order failed')
        visit.order_id, visit.token, visit.pin = data['id'], data['order_token'], data['pickup_pin']
        visit.total = Decimal(data['revenue'])
        visit.qr = Order.objects.get(pk=visit.order_id).pickup_token  # what the phone's QR code holds
        visit.chilled = self.needs_chilled(visit.order_id)
        if self.locked and visit.chilled:
            self.problem(f"Order {visit.order_id} with milk was accepted under the dairy lock")
        expected = sum(self.price(item) for item in visit.cart)
        if visit.total != expected:
            self.problem(f"Order {visit.order_id} totals {visit.total}, its drinks add up to {expected}")
        if not self.start_payment(visit):
            return self.leave(visit, 'payment failed to start')
        plan = visit.plan
        if plan == 'abandon':
            return self.leave(visit, 'walked away')
        if plan == 'cancel':
            return self.later(visit, 'cancel', self.rng.uniform(10, 60))
        if plan == 'idle':
            return self.later(visit, 'cancel', 60 + self.rng.uniform(0, 30))
        if plan == 'late_pay':
            # their bank app was slow: the money arrives after the hold ran out and the order was cancelled
            wait = (visit.hold_until - now).total_seconds() + 90 + self.rng.uniform(0, 300)
            return self.later(visit, 'pay', wait)
        if plan == 'pay_fails_then_pays':
            return self.later(visit, 'pay_fails', self.rng.uniform(15, 60))
        self.later(visit, 'pay', self.rng.uniform(15, 90))

    def price(self, item):
        if 'drink' in item:
            drink = Drink.objects.get(pk=item['drink'])
            return drink.l_price if item['size'] == 1 else drink.s_price
        ingredients = {i.code: i for i in Ingredient.objects.filter(code__in=item['custom'])}
        _, total = DesignerConfig.load().build([ingredients[c] for c in item['custom']], item['size'], item['sugar'])
        return total

    def start_payment(self, visit):
        code, data = self.api('POST', f"/ordering/orders/{visit.order_id}/payments/", {'method': 'paynow'})
        if code != 200 or Decimal(data['amount']) != visit.total:
            self.problem(f"Order {visit.order_id}: starting the payment gave {code} {data if code != 200 else ''}")
            return False
        visit.hold_until = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
        return True

    def on_cancel(self, visit, now):
        reason = 'idle_timeout' if visit.plan == 'idle' else 'customer'
        code, _ = self.api('POST', f"/ordering/orders/{visit.order_id}/cancel/",
                           {'order_token': visit.token, 'reason': reason})
        if code != 200:
            self.problem(f"Order {visit.order_id}: cancelling an unpaid order gave {code}")
        self.leave(visit, 'cancelled' if reason == 'customer' else 'kiosk timed out')

    def on_pay_fails(self, visit, now):
        order = Order.objects.get(pk=visit.order_id)
        services.payment_failed(order, 'paynow', provider_ref=f"SIM-{visit.order_id}-declined")
        if self.start_payment(visit):
            self.later(visit, 'pay', self.rng.uniform(15, 60))
        else:
            self.leave(visit, 'payment failed to start')

    def notify(self, visit, amount, ref):
        """The payment provider tells the backend money arrived (as a webhook would)."""
        order = Order.objects.get(pk=visit.order_id)
        return services.confirm_payment(order, 'paynow', amount, provider_ref=ref)

    def on_pay(self, visit, now):
        ref = f"SIM-{visit.order_id}"
        if visit.plan == 'wrong_amount' and not visit.refunds_expected:
            attempt = self.notify(visit, visit.total - Decimal('0.10'), ref + '-short')
            visit.refunds_expected += 1
            if attempt.status == PaymentAttempt.Status.SUCCEEDED:
                self.problem(f"Order {visit.order_id}: a payment 10 cents short was accepted")
            return self.later(visit, 'pay', self.rng.uniform(20, 60))
        before = Order.objects.get(pk=visit.order_id).status
        attempt = self.notify(visit, visit.total, ref)
        if visit.plan == 'late_pay':
            if before != S.CANCELLED:
                self.problem(f"Order {visit.order_id} was still {before} after its payment time ran out")
            if attempt.status == PaymentAttempt.Status.SUCCEEDED:
                visit.paid = True
                if self.locked and visit.chilled:
                    self.problem(f"Order {visit.order_id}: a late payment for a milk drink was taken under the dairy lock")
            else:
                visit.refunds_expected += 1  # sold out in the meantime: refunded
        elif attempt.status != PaymentAttempt.Status.SUCCEEDED:
            self.problem(f"Order {visit.order_id}: a correct payment came back {attempt.status}: {attempt.note}")
            return self.leave(visit, 'payment refused')
        else:
            visit.paid = True
        if visit.plan == 'pay_twice':
            again = self.notify(visit, visit.total, ref)  # the same notification sent twice
            if again.pk != attempt.pk or again.status != PaymentAttempt.Status.SUCCEEDED:
                self.problem(f"Order {visit.order_id}: a repeated payment notification was treated as new")
            second = self.notify(visit, visit.total, ref + '-again')  # the customer paid twice
            visit.refunds_expected += 1
            if second.status == PaymentAttempt.Status.SUCCEEDED:
                self.problem(f"Order {visit.order_id}: a second payment for a paid order was accepted")
        if not visit.paid:
            return self.leave(visit, 'paid late, refunded')
        if visit.plan == 'no_show':
            return self.leave(visit, 'never came')
        if visit.channel == 'phone':
            return self.later(visit, 'collect', self.rng.uniform(5, 25) * 60)
        visit.waited_since = now
        self.later(visit, 'wait', 30)

    def on_wait(self, visit, now):
        """At the kiosk, watching the order's status until it's ready."""
        code, data = self.api('GET', f"/ordering/orders/{visit.order_id}/status/")
        status = data['status']
        if status == S.READY:
            return self.collect(visit, now, visit.pin if visit.channel == 'kiosk' else visit.qr)
        if status in (S.FAILED, S.REFUND_NEEDED):
            return self.leave(visit, "couldn't be made")
        if status not in (S.PAID, S.PREPARING):
            self.problem(f"Order {visit.order_id} is {status} while its customer waits for a paid drink")
            return self.leave(visit, 'wrong status')
        if now - visit.waited_since > timedelta(minutes=30):
            return self.leave(visit, 'gave up waiting')
        self.later(visit, 'wait', 30)

    def on_collect(self, visit, now):
        """A phone customer arrives and scans their QR code straight away, ready or not."""
        visit.waited_since = now
        self.collect(visit, now, visit.qr)

    def collect(self, visit, now, code_):
        code, data = self.api('POST', '/ordering/pickup/', {'shop': self.shop.pk, 'code': code_})
        status = Order.objects.get(pk=visit.order_id).status
        if code == 200:
            if status != S.COLLECTED or data['status'] != S.COLLECTED:
                self.problem(f"Order {visit.order_id} was handed over but is {status}")
            visit.collected = True
            return self.leave(visit, 'collected')
        if code == 409 and data.get('reason') == 'preparing' and status in (S.PAID, S.PREPARING):
            return self.later(visit, 'wait', 30)
        if code == 409 and status in (S.FAILED, S.REFUND_NEEDED):
            return self.leave(visit, "couldn't be made")
        if code == 429:
            self.problem(f"Order {visit.order_id}: pickup was throttled at {self.hhmm(now)}")
            return self.leave(visit, 'throttled')
        self.problem(f"Order {visit.order_id} ({status}): pickup gave {code} {data}")
        self.leave(visit, 'pickup failed')

    # --- checks ---

    def problem(self, what):
        self.problems.append((self.day, what))

    def hhmm(self, at):
        return f"{timezone.localtime(at, SGT):%H:%M}"

    def end_of_day(self, first_order, visits):
        orders = Order.objects.filter(shop=self.shop, pk__gt=first_order)
        by_order = {v.order_id: v for v in visits if v.order_id}
        statuses = dict(orders.values_list('pk', 'status'))
        for order_id, status in statuses.items():
            visit = by_order.get(order_id)
            if visit is None:
                self.problem(f"Order {order_id} exists but no simulated customer placed it")
                continue
            want = self.expected(visit)
            if status not in want:
                self.problem(f"Order {order_id} ({visit.channel}, {visit.plan}, {visit.outcome}) is {status}, "
                             f"expected {' or '.join(sorted(want))}")
            refunds = PaymentAttempt.objects.filter(order_id=order_id, status__in=[
                PaymentAttempt.Status.REFUND_NEEDED, PaymentAttempt.Status.REFUNDED]).count()
            if status != S.REFUND_NEEDED and refunds != visit.refunds_expected:
                self.problem(f"Order {order_id}: {refunds} payment(s) marked for refund, expected {visit.refunds_expected}")
        self.check_history(orders)
        self.check_payments(orders)
        self.check_stock(orders)
        for rule in audit.check_orders():
            for ids, what in rule.problems:
                if any(i in statuses for i in ids):
                    self.problem(f"{rule.title}: order {', '.join(map(str, ids))} {what}")
        self.days.append(self.summary(visits, orders))

    def expected(self, visit):
        if visit.collected:
            return {S.COLLECTED}
        if visit.paid:
            made = self.made.get(visit.order_id)
            if made == 'READY':
                return {S.READY}
            # failed by the machine, or not made because of the dairy lock; staff refund these
            return {S.FAILED}
        return {S.CANCELLED}

    def check_history(self, orders):
        events = defaultdict(list)
        for e in OrderEvent.objects.filter(order__in=orders).order_by('at', 'pk'):
            events[e.order_id].append(e)
        for order in orders:
            history = events[order.pk]
            if not history or history[0].from_status != '' or history[0].to_status != S.PENDING:
                self.problem(f"Order {order.pk}: history doesn't start with it being placed")
                continue
            for before, after in zip(history, history[1:], strict=False):
                if after.from_status != before.to_status:
                    self.problem(f"Order {order.pk}: history jumps from {before.to_status} to a change from "
                                 f"{after.from_status}")
                if after.to_status not in TRANSITIONS.get(after.from_status, set()):
                    self.problem(f"Order {order.pk}: {after.from_status} -> {after.to_status} isn't an allowed move")
            if history[-1].to_status != order.status:
                self.problem(f"Order {order.pk} is {order.status}, its history ends at {history[-1].to_status}")

    def check_payments(self, orders):
        for order in orders.prefetch_related('payment_attempts', 'items'):
            succeeded = [a for a in order.payment_attempts.all() if a.status == PaymentAttempt.Status.SUCCEEDED]
            ever_paid = order.events.filter(to_status=S.PAID).exists()
            if order.status == S.REFUND_NEEDED:
                pass
            elif ever_paid and len(succeeded) != 1:
                self.problem(f"Order {order.pk} ({order.status}) has {len(succeeded)} succeeded payments, expected 1")
            elif not ever_paid and succeeded:
                self.problem(f"Order {order.pk} was never paid but has a succeeded payment")
            for a in succeeded:
                if a.amount != order.revenue:
                    self.problem(f"Order {order.pk}: payment of {a.amount} for a total of {order.revenue}")
            items_total = sum(i.unit_price for i in order.items.all())
            if items_total != order.revenue or order.item_quantity != len(order.items.all()):
                self.problem(f"Order {order.pk}: total {order.revenue} for {order.item_quantity} item(s), "
                             f"its items add up to {items_total}")

    def check_stock(self, orders):
        moved = dict(StockMovement.objects.filter(inventory__shop=self.shop, pk__gt=self.movements_from)
                     .values('inventory_id').annotate(t=Sum('change')).values_list('inventory_id', 't'))
        for inv in Inventory.objects.filter(shop=self.shop).select_related('ingredient'):
            expect = self.opening_stock[inv.pk] + (moved.get(inv.pk) or 0)
            if inv.current_stock != expect:
                self.problem(f"{inv.ingredient}: stock is {inv.current_stock}, its movements add up to {expect}")
            if inv.current_stock < 0:
                self.problem(f"{inv.ingredient}: stock went negative ({inv.current_stock})")
            last = inv.movements.order_by('-pk').first()
            if last and last.stock_after != inv.current_stock:
                self.problem(f"{inv.ingredient}: last movement says {last.stock_after} left, stock is {inv.current_stock}")
        for order in orders:
            holds = defaultdict(lambda: Decimal(0))
            for h in order.stock_holds.select_related('inventory'):
                holds[h.status, h.inventory.ingredient_id] += h.quantity
            used = {i: q for (s, i), q in holds.items() if s == StockHold.Status.CONSUMED}
            held = {i: q for (s, i), q in holds.items() if s == StockHold.Status.HELD}
            needs = {i: q for i, q in services.order_needs(order).items() if q}
            if order.events.filter(to_status=S.PAID).exists():
                if used != needs:
                    self.problem(f"Order {order.pk} ({order.status}) used {fmt(used)} of stock, its drinks need {fmt(needs)}")
            elif used or held:
                self.problem(f"Order {order.pk} ({order.status}) was never paid but still uses stock")

    def summary(self, visits, orders):
        outcomes = Counter(v.outcome or v.step for v in visits)
        statuses = Counter(orders.values_list('status', flat=True))
        revenue = orders.filter(status__in=[S.PAID, S.PREPARING, S.READY, S.COLLECTED]).aggregate(
            t=Sum('revenue'))['t'] or Decimal('0')
        revenue = Decimal(revenue).quantize(Decimal('0.01'))
        channels = Counter(v.channel for v in visits if v.order_id)
        low = [f"{inv.ingredient} {inv.current_stock}" for inv in
               Inventory.objects.filter(shop=self.shop).select_related('ingredient')
               if self.targets[inv.pk] and inv.current_stock < self.targets[inv.pk] * Decimal('0.1')]
        return {'day': self.day, 'customers': len(visits), 'orders': orders.count(), 'channels': channels,
                'statuses': statuses, 'outcomes': outcomes, 'revenue': revenue, 'faults': self.faults,
                'lock_spans': [(a, b) for a, b in self.lock_spans], 'low_stock': low}


def fmt(amounts):
    return '{' + ', '.join(f"{Ingredient.objects.get(pk=i).name} {q}" for i, q in sorted(amounts.items())) + '}'
