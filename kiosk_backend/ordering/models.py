from django.db import models
from operation.models import Shop, Drink

# Create your models here.

class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        TBM = 'TBM', 'To Be Made'
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    user_id = models.CharField(max_length=100, default='') # can be linked to membership program later
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    time = models.DateTimeField(auto_now_add=True)
    revenue = models.DecimalField(max_digits=6, decimal_places=2)
    item_quantity = models.PositiveSmallIntegerField(default=1)
    

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
        default=Level.ZERO,
    )
    ice = models.SmallIntegerField(
        choices=Level.choices,
        default=Level.ZERO,
    )
    drink = models.ForeignKey(Drink, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
