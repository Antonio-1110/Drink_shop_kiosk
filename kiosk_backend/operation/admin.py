from django.contrib import admin
from .models import Drink, DrinkIngredient, Shop, Ingredient, Inventory

# Register your models here.

# 1. Register the Drink Model
@admin.register(Drink)
class DrinkAdmin(admin.ModelAdmin):
    # Optional: Customize the list view for easier auditing
    list_display = ('name', 'l_price', 's_price', 'get_category_display') 
    list_editable = ('l_price', 's_price') # Allow quick price updates

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'address', 'get_shop_type_display')
    
@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'unit_of_measure')

@admin.register(DrinkIngredient)
class DrinkIngredientAdmin(admin.ModelAdmin):
    list_display = ('drink', 'ingredient', 'required_quantity')
    list_editable = ('required_quantity',)
    list_filter = ('drink',)

@admin.register(Inventory)
class DrinkIngredientAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'ingredient', 'current_stock')
    list_editable = ('current_stock',)
    list_filter = ('shop',)