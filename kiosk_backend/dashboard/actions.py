"""Changes staff can make from the dashboard. Each goes through the same code the admin and the
kiosk use, so it is checked and logged: orders through checkout.services and ordering.status
(an OrderEvent naming the staff member), stock through Inventory.adjust_stock (a StockMovement)."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from checkout.models import PaymentAttempt
from checkout.services import cancel_order, confirm_payment
from operation.models import Inventory, StockMovement
from ordering.models import Order
from ordering.status import change_status

STOCK_REASONS = {
    'restock': (StockMovement.Reason.RESTOCK, 1),
    'waste': (StockMovement.Reason.WASTE, -1),
    'count': (StockMovement.Reason.ADJUSTMENT, None),  # the amount is the new level
}


def _need(request, perm):
    if not request.user.has_perm(perm):
        raise PermissionDenied


def _back(request):
    # back to the dashboard with the same filters
    url, query = reverse('admin-dashboard'), request.POST.get('return', '')
    return redirect(url + query if query.startswith('?') else url)


@require_POST
def act(request):
    what = request.POST.get('what')
    if what == 'stock':
        _stock(request)
    elif what in ('mark_paid', 'cancel', 'collect'):
        _order(request, what)
    elif what == 'refunded':
        _refunded(request)
    else:
        messages.error(request, "Unknown change.")
    return _back(request)


def _stock(request):
    _need(request, 'operation.change_inventory')
    inventory = get_object_or_404(Inventory.objects.select_related('ingredient', 'shop'), pk=request.POST.get('inventory'))
    kind = request.POST.get('kind')
    try:
        amount = Decimal(request.POST.get('amount', ''))
    except InvalidOperation:
        amount = None
    if kind not in STOCK_REASONS or amount is None or not amount.is_finite() or amount < 0:
        messages.error(request, f"Enter an amount of {inventory.ingredient} of 0 or more.")
        return
    reason, sign = STOCK_REASONS[kind]
    change = amount * sign if sign else amount - inventory.current_stock
    if not change:
        messages.info(request, f"{inventory} is already at {inventory.current_stock} {inventory.ingredient.unit_of_measure}.")
        return
    if inventory.current_stock + change < 0:
        messages.error(request, f"There is only {inventory.current_stock} {inventory.ingredient.unit_of_measure} of {inventory}.")
        return
    inventory.adjust_stock(change, reason, note=request.POST.get('note', '')[:200], user=request.user)
    messages.success(request, f"{inventory}: {change:+} {inventory.ingredient.unit_of_measure}, "
                              f"now {inventory.current_stock}.")


def _order(request, what):
    _need(request, 'ordering.change_order')
    order = get_object_or_404(Order, pk=request.POST.get('order'))
    actor = f"staff:{request.user}"
    if what == 'mark_paid':
        # same path as the admin action: a late payment takes the stock back or is flagged for refund
        if order.status not in (Order.Status.PENDING, Order.Status.CANCELLED):
            messages.error(request, f"Order {order.pk} isn't waiting for payment.")
            return
        attempt = confirm_payment(order, 'staff', order.revenue, provider_ref=f"staff-order-{order.pk}", actor=actor)
        if attempt.status == PaymentAttempt.Status.SUCCEEDED:
            messages.success(request, f"Order {order.pk} marked as paid.")
        else:
            messages.warning(request, f"Order {order.pk} couldn't be marked paid: {attempt.note or attempt.get_status_display()}.")
    elif what == 'cancel':
        if cancel_order(order, reason="Cancelled from the dashboard.", actor=actor):
            messages.success(request, f"Order {order.pk} cancelled and its stock returned.")
        else:
            messages.error(request, f"Order {order.pk} isn't waiting for payment, so it can't be cancelled.")
    elif change_status(order, Order.Status.COLLECTED, actor=actor, reason="Handed over by staff.",
                       collected_at=timezone.now()):
        messages.success(request, f"Order {order.pk} marked as collected.")
    else:
        messages.error(request, f"Order {order.pk} isn't paid and waiting, so it can't be marked collected.")


def _refunded(request):
    _need(request, 'checkout.change_paymentattempt')
    attempt = get_object_or_404(PaymentAttempt, pk=request.POST.get('attempt'))
    if PaymentAttempt.objects.filter(pk=attempt.pk, status=PaymentAttempt.Status.REFUND_NEEDED).update(
            status=PaymentAttempt.Status.REFUNDED, updated_at=timezone.now()):
        messages.success(request, f"Payment for order {attempt.order_id} marked as refunded.")
    else:
        messages.error(request, "That payment doesn't need a refund.")
