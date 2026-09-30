"""Pickup codes: how a customer who ordered ahead (e.g. in the mobile app) collects at the machine.

Each order gets a 6-digit PIN to type on the kiosk and a random token shown as a QR code to scan.
Only the customer who placed the order sees them (in the reply to placing it). The machine hands
over an order once: it must be paid, and collecting it marks it COLLECTED.
"""
import secrets

from django.utils import timezone

from payments.paynow import qr_png_data_url
from .models import Order
from .status import change_status

# orders whose PIN is still in use; a PIN is only unique among these
UNCOLLECTED = [Order.Status.PENDING, Order.Status.PAID]


def assign_pickup_codes(order):
    """Gives a new order its PIN and token. Call inside the transaction that creates it."""
    in_use = set(Order.objects.filter(shop=order.shop, status__in=UNCOLLECTED)
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
        self.reason = reason  # for the kiosk screen: not_found, not_paid, cancelled or already_collected


def collect(shop_id, code):
    """Hands over the order a PIN or QR token belongs to. Returns the order, now COLLECTED.
    Raises PickupError (404 unknown code, 409 not paid yet or already collected)."""
    code = (code or '').strip()
    if not code:
        raise PickupError("Enter your pickup PIN or scan your QR code.", 404, "not_found")
    field = 'pickup_pin' if code.isdigit() and len(code) == 6 else 'pickup_token'
    matches = Order.objects.filter(shop_id=shop_id, **{field: code})
    order = matches.filter(status__in=UNCOLLECTED).order_by('-time').first()
    if order is None:
        latest = matches.order_by('-time').first()
        if latest and latest.status == Order.Status.COLLECTED:
            raise PickupError("This order has already been collected.", 409, "already_collected")
        if latest and latest.status == Order.Status.CANCELLED:
            raise PickupError("This order was cancelled.", 409, "cancelled")
        raise PickupError("No order found for that code at this machine.", 404, "not_found")
    if order.status == Order.Status.PENDING:
        raise PickupError("This order hasn't been paid yet.", 409, "not_paid")
    # change_status re-checks the status in the database, so two scans at once can't both collect it
    how = "PIN" if field == 'pickup_pin' else "QR code"
    if not change_status(order, Order.Status.COLLECTED, actor='kiosk', reason=f"Collected with {how}.",
                         collected_at=timezone.now()):
        raise PickupError("This order has already been collected.", 409, "already_collected")
    return order
