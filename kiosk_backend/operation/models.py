from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

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
    # drink designer: customers build their own drink from ingredients offered here
    class Kind(models.TextChoices):
        LIQUID = 'LIQUID', 'Liquid'
        TOPPING = 'TOPPING', 'Topping'
        OTHER = 'OTHER', 'Other (ice, sweetener)' # set by the ice/sugar level, never picked
    code = models.CharField(max_length=4, unique=True, null=True, blank=True) # label in drink QR codes, e.g. BT
    kind = models.CharField(max_length=7, choices=Kind.choices, default=Kind.LIQUID)
    designer_category = models.CharField(max_length=20, blank=True) # Tea, Coffee, Milk, Fruit, Toppings
    share = models.DecimalField(max_digits=4, decimal_places=2, default=1) # liquid's weight in the cup, e.g. tea 3 : milk 2 : fruit 1
    display_color = models.CharField(max_length=7, blank=True) # hex, for the cup preview
    offered_in_designer = models.BooleanField(default=False)
    designer_price = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True) # overrides the default for its kind
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
    def temperature_ok(self, temp_c=None):
        temp_c = self.last_temp_c if temp_c is None else Decimal(temp_c)
        if temp_c is None:
            return True
        if self.max_safe_temp_c is not None and temp_c > self.max_safe_temp_c:
            return False
        if self.min_safe_temp_c is not None and temp_c < self.min_safe_temp_c:
            return False
        return True
    @transaction.atomic
    def adjust_stock(self, change, reason, order=None, note='', user=None):
        # the only place stock should change, so every change is logged
        change = Decimal(change)
        Inventory.objects.filter(pk=self.pk).update(current_stock=F('current_stock') + change)
        self.refresh_from_db(fields=['current_stock'])
        return StockMovement.objects.create(
            inventory=self, change=change, stock_after=self.current_stock,
            reason=reason, order=order, note=note, created_by=user,
        )
    @transaction.atomic
    def record_temperature(self, temp_c, recorded_at=None):
        # stores the reading; an unsafe one locks the shop's kiosk until someone unlocks it
        ok = self.temperature_ok(temp_c)
        reading = TemperatureReading.objects.create(
            inventory=self, temp_c=temp_c, within_bounds=ok,
            recorded_at=recorded_at or timezone.now(),
        )
        self.last_temp_c = reading.temp_c
        self.save(update_fields=['last_temp_c'])
        if not ok:
            Kiosk.objects.filter(shop_id=self.shop_id).update(
                sfa_locked=True,
                sfa_lock_reason=f"{self.ingredient} at {reading.temp_c} C, outside safe range",
            )
        return reading
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

class StockMovement(models.Model):
    class Reason(models.TextChoices):
        ORDER = 'ORDER', 'Used by order'
        RELEASE = 'RELEASE', 'Returned from cancelled order'
        RESTOCK = 'RESTOCK', 'Restock'
        WASTE = 'WASTE', 'Waste / expired'
        ADJUSTMENT = 'ADJUST', 'Stock count adjustment'
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT, related_name='movements')
    change = models.DecimalField(max_digits=10, decimal_places=2) # negative when stock goes out
    stock_after = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=7, choices=Reason.choices)
    order = models.ForeignKey('ordering.Order', on_delete=models.PROTECT, null=True, blank=True,
                              related_name='stock_movements')
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return f"{self.change:+} {self.inventory} ({self.get_reason_display()})"

class TemperatureReading(models.Model):
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='temperature_readings')
    temp_c = models.DecimalField(max_digits=4, decimal_places=1)
    within_bounds = models.BooleanField()
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    class Meta:
        ordering = ['-recorded_at']
    def __str__(self):
        return f"{self.inventory} {self.temp_c} C at {self.recorded_at:%Y-%m-%d %H:%M}"


class DesignerConfig(models.Model):
    """Single row of drink designer settings, edited in the admin."""
    SMALL, LARGE = 0, 1 # same values as OrderItem.Size
    cup_price_small = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('2.80'))
    cup_price_large = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('3.40'))
    default_liquid_price = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.50'))
    default_topping_price = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.60'))
    # liquid in the cup without ice or sweetener, shared between the liquids picked by their share
    liquid_ml_small = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('360'))
    liquid_ml_large = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('500'))
    # toppings per cup, split evenly between the toppings picked
    topping_g_small = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('60'))
    topping_g_large = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('80'))
    # sweetener added at 100% sugar, scaled down with the sugar level
    sweetener = models.ForeignKey(Ingredient, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    sweetener_ml_small = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('30'))
    sweetener_ml_large = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('40'))

    class Meta:
        verbose_name = 'drink designer settings'
        verbose_name_plural = 'drink designer settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def price_of(self, ingredient):
        if ingredient.designer_price is not None:
            return ingredient.designer_price
        if ingredient.kind == Ingredient.Kind.TOPPING:
            return self.default_topping_price
        return self.default_liquid_price

    def build(self, ingredients, size, sugar_level, level_steps=4):
        """
        Amounts and prices for a custom drink. Returns (lines, total_price) where
        lines are (ingredient, amount, price) in each ingredient's unit_of_measure.
        """
        large = size == self.LARGE
        liquids = [i for i in ingredients if i.kind == Ingredient.Kind.LIQUID]
        toppings = [i for i in ingredients if i.kind == Ingredient.Kind.TOPPING]
        if not liquids:
            raise ValueError("A custom drink needs at least one liquid.")
        liquid_ml = self.liquid_ml_large if large else self.liquid_ml_small
        topping_g = self.topping_g_large if large else self.topping_g_small
        total_share = sum(i.share for i in liquids)
        lines = []
        for i in liquids:
            lines.append((i, (liquid_ml * i.share / total_share).quantize(Decimal('0.01')), self.price_of(i)))
        for i in toppings:
            lines.append((i, (topping_g / len(toppings)).quantize(Decimal('0.01')), self.price_of(i)))
        if self.sweetener and sugar_level:
            ml = (self.sweetener_ml_large if large else self.sweetener_ml_small) * sugar_level / level_steps
            lines.append((self.sweetener, ml.quantize(Decimal('0.01')), Decimal('0')))
        total = (self.cup_price_large if large else self.cup_price_small) + sum(p for _, _, p in lines)
        return lines, total
