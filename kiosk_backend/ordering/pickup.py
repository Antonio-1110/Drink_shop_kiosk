"""Pickup codes: how a customer who ordered ahead (e.g. in the mobile app) collects at the machine.

Each order gets a 6-digit PIN to type on the kiosk and a random token shown as a QR code to scan.
Only the customer who placed the order sees them (in the reply to placing it). The machine hands
over an order once: the drink must be READY (made), and collecting it marks it COLLECTED.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from payments.paynow import qr_png_data_url
from .models import Order
from .status import OPEN, change_status

S = Order.Status


def assign_pickup_codes(order):
    """Gives a new order its PIN and token. Call inside the transaction that creates it."""
    # a recently cancelled order can still be paid late and come back, so its PIN stays reserved
    recent = timezone.now() - timedelta(days=1)
    in_use = set(Order.objects.filter(shop=order.shop)
                 .filter(Q(status__in=OPEN) | Q(status=S.CANCELLED, time__gte=recent))
                 .exclude(pk=order.pk).values_list('pickup_pin', flat=True))
    for _ in range(50):
        pin = f"{secrets.randbelow(1_000_000):06d}"
        if pin not in in_use:
            break
    else:
        raise RuntimeError("No free pickup PIN; far too many uncollected orders at this shop.")
    order.pickup_pin = pin
    order.pickup_token = secrets.token_urlsafe(16)
    order.save(update_fields=['pickup_pin', 'pickup_token'])


def pickup_qr(order):
    # the QR code holds just the token; the kiosk's scanner sends it back as the pickup code
    return qr_png_data_url(order.pickup_token, box_size=8)


class PickupError(Exception):
    def __init__(self, message, status, reason):
        super().__init__(message)
        self.status = status
        # for the kiosk screen: not_found, not_paid, preparing, failed, refunding, cancelled or
        # already_collected
        self.reason = reason


# why an order that isn't ready can't be handed over: (message, reason)
NOT_READY = {
    S.PENDING: ("This order hasn't been paid yet.", "not_paid"),
    S.PAID: ("Your drink is still being made. Please wait a moment.", "preparing"),
    S.PREPARING: ("Your drink is still being made. Please wait a moment.", "preparing"),
    S.FAILED: ("Sorry, the machine couldn't make this drink. Staff have been told.", "failed"),
    S.REFUND_NEEDED: ("Sorry, this drink couldn't be made. Your payment is being refunded.", "refunding"),
    S.COLLECTED: ("This order has already been collected.", "already_collected"),
    S.CANCELLED: ("This order was cancelled.", "cancelled"),
}


def simulate_machine(order):
    """Stands in for the drink machine until one is connected (settings.MACHINE_SIMULATOR): a
    paid order is made at once, so it can be collected. Each step is recorded like the real one."""
    for step in (S.PREPARING, S.READY):
        change_status(order, step, actor='simulator', reason="No machine connected; made at once.")


def collect(shop_id, code):
    """Hands over the order a PIN or QR token belongs to. Returns the order, now COLLECTED.
    Raises PickupError (404 unknown code, 409 not ready yet, not made or already collected)."""
    code = (code or '').strip()
    if not code:
        raise PickupError("Enter your pickup PIN or scan your QR code.", 404, "not_found")
    field = 'pickup_pin' if code.isdigit() and len(code) == 6 else 'pickup_token'
    matches = Order.objects.filter(shop_id=shop_id, **{field: code})
    # an open order wins over an older finished one that had the same PIN
    order = matches.filter(status__in=OPEN).order_by('-time').first() or matches.order_by('-time').first()
    if order is None:
        raise PickupError("No order found for that code at this machine.", 404, "not_found")
    if order.status == S.PAID and settings.MACHINE_SIMULATOR:
        simulate_machine(order)
    if order.status != S.READY:
        message, reason = NOT_READY[order.status]
        raise PickupError(message, 409, reason)
    # change_status re-checks the status in the database, so two scans at once can't both collect it
    how = "PIN" if field == 'pickup_pin' else "QR code"
    if not change_status(order, S.COLLECTED, actor='kiosk', reason=f"Collected with {how}.",
                         collected_at=timezone.now()):
        message, reason = NOT_READY[S.COLLECTED]
        raise PickupError(message, 409, reason)
    return order
