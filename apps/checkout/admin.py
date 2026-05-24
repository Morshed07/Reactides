from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    Order,
    OrderItem,
    # OrderStatusHistory
)

# Register your models here.


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("crosscheck_id", "product", "quantity", "price", "dosage_strength", "dosage_unit", "total_price")
    can_delete = False

@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "order_id", "email", "contact_person",
        "total", "coupon_code", "shipping_coupon_code",
        "representative_name", "representative_code",
        "status", "created_at",
    )
    search_fields = ("order_id", "email", "contact_person")
    list_filter = ("status", "created_at")
    readonly_fields = ("order_id", "created_at", "updated_at")
    inlines = [OrderItemInline]

    class Meta:
        model = Order

@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = ("order", "product", "quantity", "price", "dosage_strength", "dosage_unit")
    search_fields = ("order__order_id", "product__title")
    list_filter = ("created_at",)
    
    class Meta:
        model = OrderItem

# @admin.register(OrderStatusHistory)
# class OrderStatusHistoryAdmin(ModelAdmin):
#     list_display = ("order", "status", "updated_at")
#     search_fields = ("order__order_id",)
#     list_filter = ("status", "updated_at")