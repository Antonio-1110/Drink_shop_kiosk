from django.db import models
from django.db.models import Q
from operation.models import Inventory
from ordering.models import Order


class StockHold(models.Model):
    """Ingredients taken off a shop's sellable stock for one order.

    The stock is deducted when the order is placed, so other customers can't buy it. A hold is
    released (stock put back, exactly as much as was taken) if the order is never paid, and
    consumed once it is.
    """
    class Status(models.TextChoices):
        HELD = 'HELD', 'Held'
        CONSUMED = 'CONSUMED', 'Consumed'
        RELEASED = 'RELEASED', 'Released'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='stock_holds')
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name='holds')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.quantity} {self.inventory} for order {self.order_id} ({self.status})"


class PaymentAttempt(models.Model):
    """One try at paying for an order with one payment method.

    An order's stock stays held while it has an open attempt, until that attempt's expires_at
    (set by the payment method). Every method reports success through the same code path
    (checkout.services.confirm_payment).
    """
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Waiting for payment'
        SUCCEEDED = 'SUCCEEDED', 'Paid'
        FAILED = 'FAILED', 'Failed'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUND_NEEDED = 'REFUND_NEEDED', 'Paid, needs refund'
        REFUNDED = 'REFUNDED', 'Refunded'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payment_attempts')
    method = models.CharField(max_length=20)  # a key of checkout.providers.PROVIDERS
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    # the payment method's own ID for the transaction, used to ignore repeated notifications
    provider_ref = models.CharField(max_length=100, blank=True)
    expires_at = models.DateTimeField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['method', 'provider_ref'], condition=~Q(provider_ref=''),
                                    name='unique_provider_ref_per_method'),
        ]

    def __str__(self):
        return f"{self.method} payment for order {self.order_id} ({self.status})"
