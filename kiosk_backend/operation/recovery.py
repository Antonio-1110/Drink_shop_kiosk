"""Putting things right without staff on site. Run every minute by `manage.py run_jobs`
(`manage.py recover_shops` runs it once).

Unattended vending works on one rule: a customer who paid either gets their drink or gets their
money back automatically, and a person only hears about what software can't fix. So:

- A drink the machine couldn't make (FAILED) is refunded AUTO_REFUND_FAILED_AFTER_MINUTES after it
  failed, unless the machine has started it again by then.
- A drink "being made" for far too long (STUCK_PREPARING_MINUTES + MINUTES_PER_DRINK per cup) while
  the machine keeps checking in is marked FAILED: the machine lost the order. It's then refunded as
  above. While the machine is silent we wait longer (SILENT_MACHINE_WAIT_MINUTES more): it may come back
  and finish the drink, and the edge service reports a drink cut off by a restart as FAILED itself.
- A paid order still waiting after PAID_WAIT_MAX_MINUTES while its shop can't make drinks (machine
  off or silent, a part empty, too many failures) is refunded and its ingredients go back on sale.
- A refund the payment method turned down is tried again every REFUND_RETRY_MINUTES.

Then operation/alerts.py tells staff about whatever still needs a person.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from checkout.models import PaymentAttempt
from checkout.services import refund, refund_failed_order, refund_unmade_order
from ordering.models import Order, OrderEvent
from ordering.status import change_status
from .availability import closed_reason, heartbeat_fresh
from .models import Kiosk, Shop

logger = logging.getLogger(__name__)

S = Order.Status
ACTOR = 'system'


@dataclass
class Recovered:
    stuck_failed: int = 0
    failed_refunded: int = 0
    waiting_refunded: int = 0
    refunds_retried: int = 0

    def __str__(self):
        return (f"{self.stuck_failed} stuck drink(s) failed, {self.failed_refunded} failed drink(s) refunded, "
                f"{self.waiting_refunded} waiting order(s) refunded, {self.refunds_retried} refund(s) retried")


def _since_last_change(orders):
    """{order id: when it moved to its current status}."""
    return dict(OrderEvent.objects.filter(order__in=orders).values('order_id')
                .annotate(at=Max('at')).values_list('order_id', 'at'))


def fail_stuck_orders(now):
    orders = list(Order.objects.filter(status=S.PREPARING))
    since = _since_last_change(orders)
    machines = {k.shop_id: k for k in Kiosk.objects.filter(shop__order__in=orders)}
    count = 0
    for order in orders:
        limit = timedelta(minutes=settings.STUCK_PREPARING_MINUTES
                          + settings.MINUTES_PER_DRINK * max(order.item_quantity, 1))
        kiosk = machines.get(order.shop_id)
        if kiosk is not None and kiosk.api_key_hash and not heartbeat_fresh(kiosk, now):
            limit += timedelta(minutes=settings.SILENT_MACHINE_WAIT_MINUTES)
        started = since.get(order.pk, order.time)
        if now - started < limit:
            continue
        minutes = int((now - started).total_seconds() // 60)
        if change_status(order, S.FAILED, actor=ACTOR,
                         reason=f"The machine stopped reporting on this order ({minutes} min being made)."):
            logger.error("Order %s was being made for %s min with no word from the machine; marked failed",
                         order.pk, minutes)
            count += 1
    return count


def refund_failed_orders(now):
    orders = list(Order.objects.filter(status=S.FAILED))
    since = _since_last_change(orders)
    wait = timedelta(minutes=settings.AUTO_REFUND_FAILED_AFTER_MINUTES)
    count = 0
    for order in orders:
        if now - since.get(order.pk, order.time) >= wait:
            count += refund_failed_order(order, reason="Refunded automatically.", actor=ACTOR)
    return count


def refund_long_waits(now):
    """Paid orders that have waited too long at a shop that can't make drinks right now."""
    cutoff = now - timedelta(minutes=settings.PAID_WAIT_MAX_MINUTES)
    count = 0
    for shop in Shop.objects.filter(order__status=S.PAID).distinct():
        closed = closed_reason(shop)
        if closed is None:
            continue  # the machine is working through its queue
        orders = list(Order.objects.filter(shop=shop, status=S.PAID))
        paid_at = dict(OrderEvent.objects.filter(order__in=orders, to_status=S.PAID).values('order_id')
                       .annotate(at=Max('at')).values_list('order_id', 'at'))
        for order in orders:
            if paid_at.get(order.pk, order.time) <= cutoff:
                count += refund_unmade_order(
                    order, actor=ACTOR,
                    reason=f"Refunded automatically: the shop couldn't make drinks ({closed[1]}) for too long.")
    return count


def retry_refunds(now):
    cutoff = now - timedelta(minutes=settings.REFUND_RETRY_MINUTES)
    count = 0
    for attempt in PaymentAttempt.objects.filter(status=PaymentAttempt.Status.REFUND_NEEDED, updated_at__lte=cutoff):
        refund(attempt)
        count += 1
    return count


def recover(now=None):
    """Runs every step once; returns what each did. One order's error doesn't stop the rest."""
    now = now or timezone.now()
    done = Recovered()
    for field, step in (('stuck_failed', fail_stuck_orders), ('failed_refunded', refund_failed_orders),
                        ('waiting_refunded', refund_long_waits), ('refunds_retried', retry_refunds)):
        try:
            setattr(done, field, step(now))
        except Exception:
            logger.exception("Recovery step %s failed", step.__name__)
    return done
