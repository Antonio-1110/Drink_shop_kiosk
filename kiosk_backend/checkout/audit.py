"""The daily check that orders, stock and payments add up (`manage.py check_orders`).

Each status change is checked as it happens (ordering/status.py), but a bug, a manual database
edit or a crash between steps could still leave the books out of step. Each rule below returns
the problems it finds; none of them changes anything.
"""
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Sum

from operation.models import StockMovement
from ordering.models import Order, OrderEvent
from ordering.status import OPEN, PAID_FOR
from .models import PaymentAttempt, StockHold

S = Order.Status


@dataclass
class Rule:
    title: str
    problems: list  # (order IDs, what's wrong)


def held_stock_on_finished_orders():
    holds = (StockHold.objects.filter(status=StockHold.Status.HELD).exclude(order__status=S.PENDING)
             .values('order_id', 'order__status').annotate(n=Count('id')).order_by('order_id'))
    return [([h['order_id']], f"still holds stock for {h['n']} ingredient(s) but is {h['order__status']}")
            for h in holds]


def paid_orders_without_payment():
    succeeded = PaymentAttempt.objects.filter(order=OuterRef('pk'), status=PaymentAttempt.Status.SUCCEEDED)
    refunding = PaymentAttempt.objects.filter(order=OuterRef('pk'), status__in=[
        PaymentAttempt.Status.REFUND_NEEDED, PaymentAttempt.Status.REFUNDED])
    paid = (Order.objects.filter(status__in=PAID_FOR).exclude(Exists(succeeded))
            .values_list('pk', 'status').order_by('pk'))
    problems = [([pk], f"is {status} but has no succeeded payment") for pk, status in paid]
    refunds = (Order.objects.filter(status=S.REFUND_NEEDED).exclude(Exists(refunding))
               .values_list('pk', flat=True).order_by('pk'))
    problems += [([pk], "needs a refund but no payment is marked for refunding") for pk in refunds]
    return problems


def history_out_of_step():
    last = OrderEvent.objects.filter(order=OuterRef('pk')).order_by('-at', '-pk').values('to_status')[:1]
    orders = (Order.objects.annotate(last_status=Subquery(last))
              .filter(Q(last_status__isnull=True) | ~Q(last_status=F('status')))
              .values_list('pk', 'status', 'last_status').order_by('pk'))
    return [([pk], f"is {status} but its history ends at {last_status}" if last_status
             else f"is {status} but has no status history") for pk, status, last_status in orders]


def stock_movements_out_of_step():
    # an order's stock movements (taken, then any put back) must net to what it still holds or used
    moved = defaultdict(int)
    for row in (StockMovement.objects.filter(order__isnull=False).values('order_id', 'inventory_id')
                .annotate(total=Sum('change'))):
        moved[row['order_id'], row['inventory_id']] = row['total']
    held = defaultdict(int)
    for row in (StockHold.objects.exclude(status=StockHold.Status.RELEASED).values('order_id', 'inventory_id')
                .annotate(total=Sum('quantity'))):
        held[row['order_id'], row['inventory_id']] = row['total']
    problems = []
    for key in sorted(set(moved) | set(held)):
        if moved[key] + held[key] != 0:
            order_id, inventory_id = key
            problems.append(([order_id], f"stock moved {moved[key]:+} for inventory {inventory_id}, "
                                         f"but its holds account for {-held[key]:+}"))
    return problems


def shared_pins():
    clashes = (Order.objects.filter(status__in=OPEN).exclude(pickup_pin='').values('shop_id', 'pickup_pin')
               .annotate(n=Count('id')).filter(n__gt=1).order_by('shop_id', 'pickup_pin'))
    problems = []
    for c in clashes:
        ids = list(Order.objects.filter(status__in=OPEN, shop_id=c['shop_id'], pickup_pin=c['pickup_pin'])
                   .order_by('pk').values_list('pk', flat=True))
        problems.append((ids, f"open orders at shop {c['shop_id']} share PIN {c['pickup_pin']}"))
    return problems


RULES = [
    ("Held stock only belongs to orders waiting for payment", held_stock_on_finished_orders),
    ("Every paid order has a succeeded payment", paid_orders_without_payment),
    ("The status history ends in the order's current status", history_out_of_step),
    ("Stock movements for each order add up to its holds", stock_movements_out_of_step),
    ("No two open orders at a shop share a PIN", shared_pins),
]


def check_orders():
    """Runs every rule. Returns a Rule for each one that found something."""
    return [Rule(title, problems) for title, check in RULES if (problems := check())]


def report(broken):
    if not broken:
        return "Orders, stock and payments add up. Nothing to report."
    lines = []
    for rule in broken:
        lines.append(f"{rule.title}: {len(rule.problems)} problem(s)")
        for ids, what in rule.problems:
            lines.append(f"  Order {', '.join(map(str, ids))} {what}")
    return "\n".join(lines)


def email_staff(broken):
    """Emails STAFF_ALERT_EMAILS about what was found. False if there's nobody to email."""
    if not settings.STAFF_ALERT_EMAILS:
        return False
    count = sum(len(rule.problems) for rule in broken)
    send_mail(f"Kiosk order check: {count} problem(s) found",
              "The daily check found orders, stock or payments that don't add up. Look the orders "
              "up under Orders in the admin.\n\n" + report(broken),
              None, settings.STAFF_ALERT_EMAILS)
    return True
