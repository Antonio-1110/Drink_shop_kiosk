"""The one place an order's status changes. Each change is checked against the allowed moves and
recorded as an OrderEvent, so every order has a full history."""
from django.db import transaction

from .models import Order, OrderEvent

S = Order.Status

# where each status can go next
TRANSITIONS = {
    S.PENDING: {S.PAID, S.CANCELLED},
    S.CANCELLED: {S.PAID},  # paid after the hold ran out, while the ingredients were still there
    S.PAID: {S.PREPARING},
    S.PREPARING: {S.READY, S.FAILED},
    S.READY: {S.COLLECTED},
    S.FAILED: {S.PREPARING, S.REFUND_NEEDED},  # try again, or give the money back
    S.REFUND_NEEDED: set(),
    S.COLLECTED: set(),
}

# not yet handed over, cancelled or refunded, so the order's pickup PIN is still in use
OPEN = [S.PENDING, S.PAID, S.PREPARING, S.READY, S.FAILED]
# money was taken for these, so each needs a succeeded payment
PAID_FOR = [S.PAID, S.PREPARING, S.READY, S.FAILED, S.COLLECTED]


def record_placed(order, actor='customer'):
    OrderEvent.objects.create(order=order, from_status='', to_status=order.status, actor=actor)


def change_status(order, to, *, actor, reason='', **fields):
    """Moves the order to `to` and sets any extra `fields` on it, if that move is allowed from the
    status it has in the database right now. Returns False (and changes nothing) otherwise, so two
    requests racing to change the same order can't both win."""
    with transaction.atomic():
        current = (Order.objects.select_for_update().filter(pk=order.pk)
                   .values_list('status', flat=True).first())
        if current is None or to not in TRANSITIONS[current]:
            return False
        if not Order.objects.filter(pk=order.pk, status=current).update(status=to, **fields):
            return False
        OrderEvent.objects.create(order_id=order.pk, from_status=current, to_status=to,
                                  actor=actor[:100], reason=reason[:200])
    order.status = to
    for name, value in fields.items():
        setattr(order, name, value)
    return True
