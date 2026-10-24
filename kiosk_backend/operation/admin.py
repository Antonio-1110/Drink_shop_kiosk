from django.contrib import admin
from .models import Drink, DrinkIngredient, Shop, Ingredient, Inventory, Kiosk, StockMovement, TemperatureReading, DesignerConfig

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
    list_display = ('id', 'code', 'name', 'kind', 'unit_of_measure', 'offered_in_designer', 'designer_price')
    list_filter = ('kind', 'offered_in_designer')

@admin.register(DrinkIngredient)
class DrinkIngredientAdmin(admin.ModelAdmin):
    list_display = ('drink', 'ingredient', 'required_quantity')
    list_editable = ('required_quantity',)
    list_filter = ('drink',)

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'ingredient', 'current_stock')
    list_editable = ('current_stock',)
    list_filter = ('shop',)

    def save_model(self, request, obj, form, change):
        # a stock edit here is a stock count: log it as a movement like every other stock change,
        # measured against the stock right now (orders may have used some since the page opened)
        if not (change and 'current_stock' in form.changed_data):
            return super().save_model(request, obj, form, change)
        counted = obj.current_stock
        others = [name for name in form.changed_data if name != 'current_stock']
        if others:
            obj.save(update_fields=others)
        obj.refresh_from_db(fields=['current_stock'])
        if counted != obj.current_stock:
            obj.adjust_stock(counted - obj.current_stock, StockMovement.Reason.ADJUSTMENT,
                             note="Counted in the admin.", user=request.user)

@admin.register(Kiosk)
class KioskAdmin(admin.ModelAdmin):
    list_display = ('machine_id', 'shop', 'operational_status', 'sfa_locked', 'last_heartbeat')
    list_filter = ('operational_status', 'sfa_locked')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'inventory', 'change', 'stock_after', 'reason', 'order', 'created_by')
    list_filter = ('reason', 'inventory__shop')

@admin.register(TemperatureReading)
class TemperatureReadingAdmin(admin.ModelAdmin):
    list_display = ('recorded_at', 'inventory', 'temp_c', 'within_bounds')
    list_filter = ('within_bounds', 'inventory__shop')


@admin.register(DesignerConfig)
class DesignerConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not DesignerConfig.objects.exists()
