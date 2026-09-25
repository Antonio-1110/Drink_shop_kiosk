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

class Ingredient(models.Model):
    name = models.CharField(max_length=25)
    unit_of_measure = models.CharField(max_length=10)
    # cost/supplier in the future
    def __str__(self):
        return self.name

class Inventory(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='inventories')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2)
    class Meta:
        # Ensures a shop doesn't list the same ingredient twice
        unique_together = ('shop', 'ingredient')
    def __str__(self):
        return str(self.ingredient) + " in " + str(self.shop)

class DrinkIngredient(models.Model):
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    required_quantity = models.DecimalField(max_digits=8, decimal_places=2)
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
    def __str__(self):
        return self.name