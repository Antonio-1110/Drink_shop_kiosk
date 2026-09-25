from decimal import Decimal

from django.db import models

# Create your models here.

class Shop(models.Model):
    class ShopType(models.IntegerChoices):
        F_STORE = 2, "Flagship Store"
        STORE = 1, "Normal Store"
        VENDING = 0, "Vending Machine"
    shop_type = models.SmallIntegerField(
        choices=ShopType.choices,
        default=ShopType.VENDING,
    )
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    def __str__(self):
        return self.name

class Kiosk(models.Model):
    # the dispensing machine behind a shop; inventory stays on the Shop
    class Status(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        OFFLINE = 'OFFLINE', 'Offline'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='kiosk')
    machine_id = models.CharField(max_length=50, unique=True)
    operational_status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    # software lock for food safety (SFA), e.g. dairy above its safe temperature
    sfa_locked = models.BooleanField(default=False)
    sfa_lock_reason = models.CharField(max_length=200, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return self.machine_id + " @ " + str(self.shop)

class Ingredient(models.Model):
    class Viscosity(models.IntegerChoices):
        WATER_LIKE = 1, "Water-like"
        LOW = 2, "Low"
        MEDIUM = 3, "Medium (milk, light syrup)"
        HIGH = 4, "High (thick syrup, puree)"
    name = models.CharField(max_length=25)
    unit_of_measure = models.CharField(max_length=10)
    density_factor = models.DecimalField(max_digits=5, decimal_places=3, default=Decimal('1.000')) # g per mL
    viscosity_rating = models.SmallIntegerField(
        choices=Viscosity.choices,
        default=Viscosity.WATER_LIKE,
    )
    reorder_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0) # in unit_of_measure
    # nutrition per 100 unit_of_measure (per 100 mL or per 100 g), used for Nutri-Grade
    sugar_per_100 = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    saturated_fat_per_100 = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    contains_sweetener = models.BooleanField(default=False) # non-sugar sweetener, rules out grade A
    exclude_from_grade = models.BooleanField(default=False) # e.g. toppings, declared separately
    # cost/supplier in the future
    def to_millilitres(self, quantity):
        # quantities in grams are converted by density, everything else is taken as mL
        if self.unit_of_measure.strip().lower() in ('g', 'gram', 'grams'):
            return Decimal(quantity) / self.density_factor
        return Decimal(quantity)
    def __str__(self):
        return self.name

class Inventory(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='inventories')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2)
    # safe storage bounds, e.g. max 4 C for dairy; null means no limit
    min_safe_temp_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    max_safe_temp_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    last_temp_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    last_cip_cleaned_at = models.DateTimeField(null=True, blank=True) # clean-in-place
    class Meta:
        # Ensures a shop doesn't list the same ingredient twice
        unique_together = ('shop', 'ingredient')
    def needs_reorder(self):
        return self.current_stock <= self.ingredient.reorder_threshold
    def temperature_ok(self):
        if self.last_temp_c is None:
            return True
        if self.max_safe_temp_c is not None and self.last_temp_c > self.max_safe_temp_c:
            return False
        if self.min_safe_temp_c is not None and self.last_temp_c < self.min_safe_temp_c:
            return False
        return True
    def __str__(self):
        return str(self.ingredient) + " in " + str(self.shop)

class DrinkIngredient(models.Model):
    class Scaling(models.IntegerChoices):
        # which customer setting multiplies required_quantity
        FIXED = 0, "Fixed"
        SUGAR = 1, "Sugar level"
        ICE = 2, "Ice level"
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    required_quantity = models.DecimalField(max_digits=8, decimal_places=2)
    scaling = models.SmallIntegerField(
        choices=Scaling.choices,
        default=Scaling.FIXED,
    )
    drink = models.ForeignKey('Drink', on_delete=models.CASCADE, related_name='required')
    class Meta:
        # Ensures a drink doesn't list the same ingredient twice
        unique_together = ('drink', 'ingredient')
    def __str__(self):
        return str(self.ingredient) + " for " + str(self.drink)


class Drink(models.Model):
    class Category(models.IntegerChoices):
        MILK_TEA = 1, "Milk Tea"
        FRUIT_TEA = 2, "Fruit Tea"
        SMOOTHIE = 3, "Smoothie"
        COFFEE = 4, "Coffee"
        OTHERS = 0, "Others"
    category = models.SmallIntegerField(
        choices=Category.choices,
        default=Category.OTHERS,
    )
    name = models.CharField(max_length=100)
    image_url = models.CharField(max_length=200, blank=True) # need no internet solution
    l_price = models.DecimalField(max_digits=4, decimal_places=2)
    s_price = models.DecimalField(max_digits=4, decimal_places=2)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True) # retired drinks stay for order history
    def __str__(self):
        return self.name