from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from operation.models import Shop, Ingredient, Inventory, Drink, DrinkIngredient, DesignerConfig

# Demo menu for local development. Safe to run again: it tops stock back up to these levels
# and leaves anything you added yourself alone.
# NOTE: written against the current models; update it when the Kiosk/Recipe model changes land.

SHOPS = [
    ("Demo Kiosk - Tampines", "10 Tampines Central 1, Singapore 529536", Shop.ShopType.VENDING),
    ("Demo Store - Bugis", "200 Victoria Street, Singapore 188021", Shop.ShopType.STORE),
]

L, T, O = Ingredient.Kind.LIQUID, Ingredient.Kind.TOPPING, Ingredient.Kind.OTHER

INGREDIENTS = [
    # name, unit, stock at each shop, then the designer and nutrition details:
    # code, kind, designer category, share, colour, sugar and saturated fat per 100 mL or g
    ("Black tea", "mL", 20000, "BT", L, "Tea", 3, "#8a4b24", 0, 0),
    ("Green tea", "mL", 15000, "GT", L, "Tea", 3, "#9bb35c", 0, 0),
    ("Oolong tea", "mL", 10000, "OT", L, "Tea", 3, "#b07a3c", 0, 0),
    ("Fresh milk", "mL", 8000, "FM", L, "Milk", 2, "#f3ede0", 4.8, 2.3),
    ("Oat milk", "mL", 4000, "OM", L, "Milk", 2, "#e8dcc4", 4.0, 0.3),
    ("Brown sugar syrup", "mL", 2000, "BS", O, "", 1, "#a0612b", 65, 0),
    ("Tapioca pearls", "g", 3000, "TP", T, "Toppings", 1, "#3b2417", 0, 0),
    ("Passion fruit", "g", 1500, "PF", L, "Fruit", 1, "#e8b53a", 11, 0),
    ("Lemon", "g", 1000, "LM", L, "Fruit", 1, "#f5e663", 2.5, 0),
    ("Mango puree", "g", 500, "MG", L, "Fruit", 1, "#f4a52a", 14, 0),  # low on purpose: runs out after a few mango drinks
    ("Espresso", "mL", 3000, "ES", L, "Coffee", 1, "#4a2c1d", 0, 0),
    ("Ice", "g", 50000, "", O, "", 1, "", 0, 0),
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
        for name, unit, stock, code, kind, category, share, color, sugar, sat_fat in INGREDIENTS:
            ingredient, _ = Ingredient.objects.get_or_create(name=name, defaults={"unit_of_measure": unit})
            # fill in designer details only where they're still blank, so your own edits stay
            if not ingredient.code and code:
                ingredient.code, ingredient.kind, ingredient.designer_category = code, kind, category
                ingredient.share, ingredient.display_color = Decimal(share), color
                ingredient.offered_in_designer = kind != O
                ingredient.sugar_per_100, ingredient.saturated_fat_per_100 = Decimal(str(sugar)), Decimal(str(sat_fat))
                ingredient.save()
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

        config = DesignerConfig.load()
        if config.sweetener is None:
            config.sweetener = ingredients["Brown sugar syrup"]
            config.save()

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(shops)} shops, {len(INGREDIENTS)} ingredients, {len(DRINKS)} drinks."))
        if shops[0].id != 1:
            # the kiosk UI shows shop 1 unless told otherwise
            self.stdout.write(f"Start the kiosk UI with VITE_SHOP_ID={shops[0].id} to see {shops[0].name}.")
