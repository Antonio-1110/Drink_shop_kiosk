from django.contrib import admin
from .models import Order, OrderItem
from .utils import mark_order_paid, cancel_order


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('drink', 'size', 'sugar', 'ice')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'time', 'revenue', 'item_quantity', 'status')
    list_filter = ('status', 'shop')
    readonly_fields = ('shop', 'time', 'revenue', 'item_quantity', 'user_id', 'status')
    inlines = [OrderItemInline]
    actions = ['mark_paid', 'cancel_and_restock']

    # status only changes through the actions, so stock always stays in step with it
    def has_add_permission(self, request):
        return False

    # orders are sales records; cancel instead of deleting
    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected pending orders as paid")
    def mark_paid(self, request, queryset):
        count = sum(mark_order_paid(order) for order in queryset)
        self.message_user(request, f"Marked {count} order(s) as paid. Orders that weren't pending were skipped.")

    @admin.action(description="Cancel selected pending orders and return their stock")
    def cancel_and_restock(self, request, queryset):
        count = sum(cancel_order(order) for order in queryset)
        self.message_user(request, f"Cancelled {count} order(s). Orders that weren't pending were skipped.")
