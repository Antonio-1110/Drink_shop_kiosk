from django.db import models
from operation.models import Shop, Drink

# Create your models here.

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        TBM = 'TBM', 'To Be Made'
        PAID = 'PAID', 'Paid / Ready for Dispense'
        COLLECTED = 'COLLECTED', 'Collected'
    status = models.CharField(
        max_length=10,
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
    drink = models.ForeignKey(Drink, on_delete=models.PROTECT) # retire drinks with is_active instead
    unit_price = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True) # price at time of sale
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    custom_settings = models.JSONField(default=dict, blank=True)
    # Nutri-Grade applied when the item was ordered, see operation.health_metrics
    nutri_grade = models.CharField(max_length=1, blank=True)
    sugar_g_per_100ml = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saturated_fat_g_per_100ml = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    def apply_nutri_grade(self):
        from operation.health_metrics import grade_drink
        result = grade_drink(self.drink, sugar_level=self.sugar, ice_level=self.ice)
        self.nutri_grade = result.grade
        self.sugar_g_per_100ml = result.sugar_g_per_100ml
        self.saturated_fat_g_per_100ml = result.saturated_fat_g_per_100ml
        return result
