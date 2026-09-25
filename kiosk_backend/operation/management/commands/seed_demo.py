from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from operation.models import Shop, Ingredient, Inventory, Drink, DrinkIngredient

# Demo menu for local development. Safe to run again: it tops stock back up to these levels
# and leaves anything you added yourself alone.
# NOTE: written against the current models; update it when the Kiosk/Recipe model changes land.

SHOPS = [
    ("Demo Kiosk - Tampines", "10 Tampines Central 1, Singapore 529536", Shop.ShopType.VENDING),
    ("Demo Store - Bugis", "200 Victoria Street, Singapore 188021", Shop.ShopType.STORE),
]

INGREDIENTS = [  # name, unit, stock at each shop
    ("Black tea", "mL", 20000),
    ("Green tea", "mL", 15000),
    ("Oolong tea", "mL", 10000),
    ("Fresh milk", "mL", 8000),
    ("Oat milk", "mL", 4000),
    ("Brown sugar syrup", "mL", 2000),
    ("Tapioca pearls", "g", 3000),
    ("Passion fruit", "g", 1500),
    ("Lemon", "g", 1000),
    ("Mango puree", "g", 500),  # low on purpose: runs out after a few mango drinks
    ("Espresso", "mL", 3000),
    ("Ice", "g", 50000),
]

DRINKS = [  # name, category, small price, large price, description, recipe
    ("Classic Milk Tea", Drink.Category.MILK_TEA, "3.80", "4.60", "Black tea with fresh milk.",
     {"Black tea": 250, "Fresh milk": 80, "Ice": 150}),
    ("Brown Sugar Pearl Milk", Drink.Category.MILK_TEA, "4.80", "5.60", "Fresh milk, brown sugar and chewy pearls.",
     {"Fresh milk": 250, "Brown sugar syrup": 30, "Tapioca pearls": 60, "Ice": 100}),
    ("Oolong Oat Latte", Drink.Category.MILK_TEA, "4.50", "5.30", "Roasted oolong with oat milk.",
     {"Oolong tea": 250, "Oat milk": 100, "Ice": 150}),
    ("Passion Fruit Green Tea", Drink.Category.FRUIT_TEA, "3.90", "4.70", "Green tea shaken with passion fruit.",
     {"Green tea": 300, "Passion fruit": 60, "Ice": 150}),
    ("Lemon Black Tea", Drink.Category.FRUIT_TEA, "3.20", "3.90", "Black tea with fresh lemon.",
     {"Black tea": 300, "Lemon": 40, "Ice": 150}),
    ("Mango Smoothie", Drink.Category.SMOOTHIE, "5.20", "6.00", "Blended mango and ice.",
     {"Mango puree": 150, "Fresh milk": 50, "Ice": 200}),
    ("Iced Latte", Drink.Category.COFFEE, "4.20", "5.00", "Espresso over fresh milk and ice.",
     {"Espresso": 60, "Fresh milk": 200, "Ice": 150}),
    ("Iced Oolong Tea", Drink.Category.OTHERS, "2.80", "3.40", "Unsweetened oolong.",
     {"Oolong tea": 350, "Ice": 150}),
]


class Command(BaseCommand):
    help = "Load demo shops, ingredients, stock and drinks for local development."

    @transaction.atomic
    def handle(self, *args, **options):
        shops = []
        for name, address, shop_type in SHOPS:
            shop, _ = Shop.objects.get_or_create(name=name, defaults={"address": address, "shop_type": shop_type})
            shops.append(shop)

        ingredients = {}
        for name, unit, stock in INGREDIENTS:
            ingredient, _ = Ingredient.objects.get_or_create(name=name, defaults={"unit_of_measure": unit})
            ingredients[name] = ingredient
            for shop in shops:
                Inventory.objects.update_or_create(
                    shop=shop, ingredient=ingredient, defaults={"current_stock": Decimal(stock)})

        for name, category, s_price, l_price, description, recipe in DRINKS:
            drink, _ = Drink.objects.get_or_create(name=name, defaults={
                "category": category, "s_price": Decimal(s_price), "l_price": Decimal(l_price),
                "description": description})
            for ingredient_name, quantity in recipe.items():
                DrinkIngredient.objects.update_or_create(
                    drink=drink, ingredient=ingredients[ingredient_name],
                    defaults={"required_quantity": Decimal(quantity)})

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(shops)} shops, {len(INGREDIENTS)} ingredients, {len(DRINKS)} drinks."))
        if shops[0].id != 1:
            # the kiosk UI shows shop 1 unless told otherwise
            self.stdout.write(f"Start the kiosk UI with VITE_SHOP_ID={shops[0].id} to see {shops[0].name}.")
