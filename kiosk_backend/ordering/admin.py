from django.contrib import admin
from checkout.models import PaymentAttempt
from checkout.services import cancel_order, confirm_payment
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('drink', 'size', 'sugar', 'ice')
    can_delete = False


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    fields = readonly_fields = ('method', 'status', 'amount', 'provider_ref', 'expires_at', 'note')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'time', 'revenue', 'item_quantity', 'status')
    list_filter = ('status', 'shop')
    readonly_fields = ('shop', 'time', 'revenue', 'item_quantity', 'user_id', 'status')
    inlines = [OrderItemInline, PaymentAttemptInline]
    actions = ['mark_paid', 'cancel_and_restock']

    # status only changes through the actions, so stock always stays in step with it
    def has_add_permission(self, request):
        return False

    # orders are sales records; cancel instead of deleting
    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected orders as paid (payment checked by staff)")
    def mark_paid(self, request, queryset):
        # goes through the same path as every payment method, so a late payment on a cancelled
        # order takes the stock back if it's still there, or is flagged for a refund
        unpaid = queryset.filter(status__in=[Order.Status.PENDING, Order.Status.CANCELLED])
        results = [confirm_payment(order, 'staff', order.revenue, provider_ref=f"staff-order-{order.pk}")
                   for order in unpaid]
        paid = sum(a.status == PaymentAttempt.Status.SUCCEEDED for a in results)
        self.message_user(request, f"Marked {paid} order(s) as paid. "
                                   f"{len(results) - paid} couldn't be (see their payment notes); "
                                   f"{queryset.count() - len(results)} weren't unpaid.")

    @admin.action(description="Cancel selected unpaid orders and return their stock")
    def cancel_and_restock(self, request, queryset):
        count = sum(cancel_order(order, reason=f"Cancelled by {request.user}.") for order in queryset)
        self.message_user(request, f"Cancelled {count} order(s). Orders that weren't unpaid were skipped.")
