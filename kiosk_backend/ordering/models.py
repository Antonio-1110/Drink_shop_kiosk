from django.db import models
from operation.models import Shop, Drink, Ingredient

# Create your models here.

class Order(models.Model):
    # how an order moves: PENDING -> PAID -> PREPARING -> READY -> COLLECTED, or PENDING -> CANCELLED.
    # A payment that arrives after the order was cancelled can still make it PAID. A drink the
    # machine couldn't make is FAILED, then retried (PREPARING again) or refunded (REFUND_NEEDED).
    # Change it only through ordering.status.change_status, which checks the move and records it
    # as an OrderEvent.
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Waiting for payment'
        PAID = 'PAID', 'Paid'
        PREPARING = 'PREPARING', 'Being made'
        READY = 'READY', 'Ready to collect'
        FAILED = 'FAILED', "Couldn't be made"
        REFUND_NEEDED = 'REFUND_NEEDED', 'Not made, refund needed'
        COLLECTED = 'COLLECTED', 'Collected'
        CANCELLED = 'CANCELLED', 'Cancelled'
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
    )
    user_id = models.CharField(max_length=100, default='') # can be linked to membership program later
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # keep sales history
    time = models.DateTimeField(auto_now_add=True)
    revenue = models.DecimalField(max_digits=6, decimal_places=2)
    item_quantity = models.PositiveSmallIntegerField(default=1)
    payment_reference = models.CharField(max_length=100, blank=True) # SGQR / GrabPay transaction id
    # pickup at the machine: 6-digit PIN typed on the kiosk, or token behind a QR code
    pickup_pin = models.CharField(max_length=6, blank=True, db_index=True)
    pickup_token = models.CharField(max_length=32, blank=True, db_index=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    

class OrderItem(models.Model):
    class Size(models.IntegerChoices): # can add more sizes later
        LARGE = 1, "Large"
        SMALL = 0, "Small"
    class Level(models.IntegerChoices):
        NORMAL = 4, '100%',
        TQ = 3, '75%'
        HALF = 2, '50%'
        QUARTER = 1, '25%'
        ZERO = 0, '0%'
    size = models.SmallIntegerField(
        choices=Size.choices,
        default=Size.SMALL,
    )
    sugar = models.SmallIntegerField(
        choices=Level.choices,
        default=Level.NORMAL,
    )
    ice = models.SmallIntegerField(
        choices=Level.choices,
        default=Level.NORMAL,
    )
    drink = models.ForeignKey(Drink, on_delete=models.PROTECT, null=True, blank=True) # empty for designer drinks; retire menu drinks with is_active
    unit_price = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True) # price at time of sale
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    custom_settings = models.JSONField(default=dict, blank=True)
    # Nutri-Grade applied when the item was ordered, see operation.health_metrics
    nutri_grade = models.CharField(max_length=1, blank=True)
    sugar_g_per_100ml = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saturated_fat_g_per_100ml = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    def apply_nutri_grade(self):
        from operation.health_metrics import grade_drink, grade_ingredient_lines
        if self.drink_id:
            result = grade_drink(self.drink, sugar_level=self.sugar, ice_level=self.ice)
        else:
            result = grade_ingredient_lines(
                (line.ingredient, line.amount) for line in self.custom_ingredients.select_related('ingredient'))
        self.nutri_grade = result.grade
        self.sugar_g_per_100ml = result.sugar_g_per_100ml
        self.saturated_fat_g_per_100ml = result.saturated_fat_g_per_100ml
        return result


class OrderItemIngredient(models.Model):
    # one ingredient of a designer drink, with the amount and price it was sold at
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='custom_ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=8, decimal_places=2) # in the ingredient's unit_of_measure
    unit_price = models.DecimalField(max_digits=4, decimal_places=2)


class OrderEvent(models.Model):
    """One change in an order's status, kept as its history: what changed, when, who did it, why."""
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='events')
    from_status = models.CharField(max_length=15, blank=True)  # empty when the order was placed
    to_status = models.CharField(max_length=15, choices=Order.Status.choices)
    at = models.DateTimeField(auto_now_add=True)
    # customer, kiosk, machine:<machine_id>, system (automatic), payment:<method> or staff:<username>
    actor = models.CharField(max_length=100, blank=True)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['at', 'pk']

    def __str__(self):
        return f"Order {self.order_id}: {self.from_status or 'placed'} -> {self.to_status}"
