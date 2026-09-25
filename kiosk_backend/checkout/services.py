"""Holding stock for unpaid orders and turning payments into paid orders.

The rules:
- Placing an order takes its ingredients off sellable stock (a StockHold per ingredient).
- The hold lasts while the order has an open PaymentAttempt, until that attempt expires. Each
  payment method sets its own time limit. With no open attempt (not started yet, or the last one
  failed), the customer gets PAYMENT_START_GRACE_MINUTES to start one. ORDER_MAX_HOLD_MINUTES caps
  the whole thing so an order can't hold stock forever.
- Cancelling (customer taps Cancel, or the hold runs out) puts the stock back.
- Before an expired attempt is given up on, the payment method is asked whether it was paid after
  all, so a missed notification never cancels a paid order.
- Every payment method confirms payment through confirm_payment. A payment that arrives after its
  order was cancelled gets the stock back if there is still enough, and is refunded if not.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from operation.models import Inventory
from ordering.models import Order
from ordering.utils import aggregate_ingredients, check_cart_fulfillment
from .models import PaymentAttempt, StockHold
from .providers import PROVIDERS, SUCCEEDED, FAILED

logger = logging.getLogger(__name__)

# the Order model will get a proper Paid status; until then TBM ("to be made") means paid
PAID = getattr(Order.Status, 'PAID', Order.Status.TBM)

TOKEN_SALT = 'checkout.order'


class CheckoutError(Exception):
    pass


# --- order tokens: proof that the caller placed the order (order IDs are guessable) ---

def order_token(order):
    return signing.dumps(order.pk, salt=TOKEN_SALT)


def check_order_token(order, token):
    try:
        return signing.loads(token or '', salt=TOKEN_SALT) == order.pk
    except signing.BadSignature:
        return False


# --- stock holds ---

def order_cart(order):
    return list(order.items.values_list('drink_id', flat=True))


def hold_stock(order, cart=None):
    """Takes the order's ingredients off sellable stock. Call inside a transaction, after locking
    the shop's inventory rows and checking there is enough."""
    needed = aggregate_ingredients(cart if cart is not None else order_cart(order))
    inventories = Inventory.objects.filter(shop=order.shop, ingredient_id__in=needed)
    for inventory in inventories:
        quantity = needed[inventory.ingredient_id]
        Inventory.objects.filter(pk=inventory.pk).update(current_stock=F('current_stock') - quantity)
        StockHold.objects.create(order=order, inventory=inventory, quantity=quantity)


def release_stock(order):
    for hold in order.stock_holds.select_for_update().filter(status=StockHold.Status.HELD):
        Inventory.objects.filter(pk=hold.inventory_id).update(current_stock=F('current_stock') + hold.quantity)
        hold.status = StockHold.Status.RELEASED
        hold.save(update_fields=['status', 'updated_at'])


def consume_stock(order):
    order.stock_holds.filter(status=StockHold.Status.HELD).update(
        status=StockHold.Status.CONSUMED, updated_at=timezone.now())


def hold_expires_at(order):
    """When the order's stock is released if it still isn't paid."""
    attempts = order.payment_attempts.all()
    open_until = attempts.filter(status=PaymentAttempt.Status.OPEN).aggregate(t=Max('expires_at'))['t']
    if open_until is None:
        # not started yet, or the last try failed: a short while to start (another) payment.
        # An attempt that simply expired earns no extra time.
        failed_at = attempts.filter(status=PaymentAttempt.Status.FAILED).aggregate(t=Max('updated_at'))['t']
        start = max(order.time, failed_at) if failed_at else order.time
        open_until = start + timedelta(minutes=settings.PAYMENT_START_GRACE_MINUTES)
    return min(open_until, order.time + timedelta(minutes=settings.ORDER_MAX_HOLD_MINUTES))


# --- payments ---

def start_payment(order, method):
    """Opens (or reuses) a payment attempt; returns (attempt, what the customer needs to pay)."""
    provider = PROVIDERS[method]
    now = timezone.now()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != Order.Status.PENDING:
            raise CheckoutError("This order is no longer waiting for payment.")
        attempt = order.payment_attempts.filter(
            method=method, status=PaymentAttempt.Status.OPEN, expires_at__gt=now).first()
        if attempt is None:
            limit = order.time + timedelta(minutes=settings.ORDER_MAX_HOLD_MINUTES)
            expires_at = min(now + timedelta(minutes=provider.hold_minutes), limit)
            if expires_at <= now:
                raise CheckoutError("This order has run out of time to be paid.")
            attempt = PaymentAttempt.objects.create(
                order=order, method=method, amount=order.revenue, expires_at=expires_at)
    return attempt, provider.start(attempt)


def cancel_order(order, reason=''):
    """Cancels an unpaid order and puts its stock back. False if it wasn't pending."""
    with transaction.atomic():
        if not Order.objects.filter(pk=order.pk, status=Order.Status.PENDING).update(
                status=Order.Status.CANCELLED):
            return False
        for attempt in order.payment_attempts.filter(status=PaymentAttempt.Status.OPEN):
            PROVIDERS[attempt.method].cancel(attempt)
            attempt.status = PaymentAttempt.Status.CANCELLED
            attempt.note = reason[:200]
            attempt.save(update_fields=['status', 'note', 'updated_at'])
        release_stock(order)
    return True


def confirm_payment(order, method, amount, provider_ref=''):
    """Records that money arrived. The one path every payment method uses. Safe to call twice
    for the same provider_ref. Returns the attempt; its status says what happened:
    SUCCEEDED (order is paid) or REFUND_NEEDED / REFUNDED (we couldn't take the payment)."""
    provider = PROVIDERS[method]
    amount = Decimal(str(amount))
    with transaction.atomic():
        if provider_ref:
            seen = PaymentAttempt.objects.filter(method=method, provider_ref=provider_ref).first()
            if seen and seen.status != PaymentAttempt.Status.OPEN:
                return seen  # a repeated notification
        order = Order.objects.select_for_update().get(pk=order.pk)
        attempt = (order.payment_attempts.select_for_update()
                   .filter(method=method, status__in=[PaymentAttempt.Status.OPEN, PaymentAttempt.Status.EXPIRED,
                                                      PaymentAttempt.Status.CANCELLED])
                   .order_by('-created_at').first())
        if attempt is None:
            attempt = PaymentAttempt(order=order, method=method, amount=order.revenue, expires_at=timezone.now())
        attempt.amount = amount
        attempt.provider_ref = provider_ref

        problem = None
        if amount != order.revenue:
            problem = f"Paid {amount}, order total is {order.revenue}."
        elif order.status == Order.Status.PENDING:
            Order.objects.filter(pk=order.pk).update(status=PAID)
            consume_stock(order)
        elif order.status == Order.Status.CANCELLED:
            # paid after the hold ran out: take the order if the stock is still there
            list(Inventory.objects.select_for_update().filter(shop=order.shop))
            cart = order_cart(order)
            if check_cart_fulfillment(order.shop, cart)[0]:
                hold_stock(order, cart)
                Order.objects.filter(pk=order.pk).update(status=PAID)
                consume_stock(order)
            else:
                problem = "Paid after the order was cancelled, and the ingredients have sold out."
        else:
            problem = f"Order was already {order.get_status_display().lower()}."

        if problem is None:
            attempt.status = PaymentAttempt.Status.SUCCEEDED
        else:
            attempt.status = PaymentAttempt.Status.REFUND_NEEDED
            attempt.note = problem
        attempt.save()

    if attempt.status == PaymentAttempt.Status.REFUND_NEEDED:
        refund(attempt)
    return attempt


def refund(attempt):
    try:
        refunded = PROVIDERS[attempt.method].refund(attempt)
    except Exception:
        logger.exception("Refund failed for payment attempt %s", attempt.pk)
        refunded = False
    if refunded:
        PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.Status.REFUNDED)
        attempt.status = PaymentAttempt.Status.REFUNDED
    else:
        # staff see these in the admin under Payment attempts, "Paid, needs refund"
        logger.error("Order %s: payment %s needs a refund by staff: %s",
                     attempt.order_id, attempt.pk, attempt.note)


def payment_failed(order, method, provider_ref=''):
    PaymentAttempt.objects.filter(order=order, method=method, status=PaymentAttempt.Status.OPEN).update(
        status=PaymentAttempt.Status.FAILED, provider_ref=provider_ref, updated_at=timezone.now())


def expire_unpaid_orders(shop=None):
    """Cancels unpaid orders whose hold has run out and returns their stock. Checks with each
    payment method first, so a payment we weren't told about still counts. Returns how many
    orders were cancelled."""
    now = timezone.now()
    pending = Order.objects.filter(status=Order.Status.PENDING)
    if shop is not None:
        pending = pending.filter(shop=shop)
    cancelled = 0
    for order in pending:
        for attempt in order.payment_attempts.filter(status=PaymentAttempt.Status.OPEN, expires_at__lte=now):
            result = PROVIDERS[attempt.method].check_status(attempt)
            if result == SUCCEEDED:
                confirm_payment(order, attempt.method, attempt.amount, attempt.provider_ref)
            elif result == FAILED:
                payment_failed(order, attempt.method)
            else:
                PaymentAttempt.objects.filter(pk=attempt.pk, status=PaymentAttempt.Status.OPEN).update(
                    status=PaymentAttempt.Status.EXPIRED, updated_at=now)
        order.refresh_from_db()
        if order.status == Order.Status.PENDING and hold_expires_at(order) <= now:
            cancelled += cancel_order(order, reason="Not paid in time.")
    return cancelled
