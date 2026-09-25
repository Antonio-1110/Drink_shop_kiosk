from django.contrib import admin
from .models import PaymentAttempt, StockHold


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'method', 'status', 'amount', 'provider_ref', 'expires_at', 'note')
    list_filter = ('status', 'method')
    readonly_fields = [f.name for f in PaymentAttempt._meta.fields]
    actions = ['mark_refunded']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected payments as refunded (after refunding them yourself)")
    def mark_refunded(self, request, queryset):
        count = queryset.filter(status=PaymentAttempt.Status.REFUND_NEEDED).update(
            status=PaymentAttempt.Status.REFUNDED)
        self.message_user(request, f"Marked {count} payment(s) as refunded.")


@admin.register(StockHold)
class StockHoldAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'inventory', 'quantity', 'status', 'updated_at')
    list_filter = ('status',)
    readonly_fields = [f.name for f in StockHold._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
