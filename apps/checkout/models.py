from django.db import models, transaction
from apps.core.models import BaseModel
from decimal import Decimal
import datetime
from apps.product.models import Product
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

# Choices
ORDER_STATUS = (
    ('Placed', 'Placed'),
    ('Processing', 'Processing'),
    ('Shipped', 'Shipped'),
    ('Delivered', 'Delivered'),
    ('Canceled', 'Canceled')
)

PAYMENT_METHOD = (
    ('cash_on_delivery', 'Cash On Delivery'),
    ('bank_transfer', 'Bank Transfer'),
    ('zelle_payment', 'Zelle Payment')
)


class Order(models.Model):
    order_id = models.CharField(max_length=20, unique=True, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    contact_person = models.CharField(max_length=250)
    email = models.EmailField(max_length=150)
    mobile_number = models.CharField(max_length=14)
    address = models.TextField()
    city = models.CharField(max_length=150, blank=True, null=True)
    state = models.CharField(max_length=150, blank=True, null=True)
    zip_code = models.CharField(max_length=150, blank=True, null=True)
    payment_method = models.CharField(max_length=150, choices=PAYMENT_METHOD)
    representative_name = models.CharField(max_length=250, blank=True, null=True)
    representative_code = models.CharField(max_length=50, blank=True, null=True)

    coupon_discount = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    shipping_charge = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    shipping_discount = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    shipping_coupon_code = models.CharField(max_length=50, null=True, blank=True)
    
    status = models.CharField(max_length=250, choices=ORDER_STATUS, default='Placed')

    paid = models.BooleanField(default=False)
    sub_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Orders'

    def save(self, *args, **kwargs):
        # 1. Generate Custom Order ID (thread-safe with atomic transaction)
        if not self.order_id:
            with transaction.atomic():
                year = datetime.date.today().year
                # Use select_for_update to lock and ensure unique order_id
                last_order = Order.objects.select_for_update().filter(
                    created_at__year=year
                ).order_by('-created_at').first()
                
                if last_order and last_order.order_id:
                    try:
                        # Extract counter from last order (e.g., ORD-2026-0001 -> 1)
                        counter = int(last_order.order_id.split('-')[-1])
                        order_count = counter + 1
                    except (ValueError, IndexError):
                        order_count = Order.objects.filter(created_at__year=year).count() + 1
                else:
                    order_count = Order.objects.filter(created_at__year=year).count() + 1
                
                self.order_id = f"ORD-{year}-{str(order_count).zfill(4)}"

        # # 2. Track Status History
        # if self.pk:
        #     original = Order.objects.get(pk=self.pk)
        #     if original.status != self.status:
        #         OrderStatusHistory.objects.create(
        #             order=self,
        #             status=self.status
        #         )
        
        super(Order, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.contact_person}"


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, related_name='orderitems', on_delete=models.CASCADE)
    crosscheck_id = models.CharField(max_length=20, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    dosage_strength = models.CharField(max_length=50)
    dosage_unit = models.CharField(max_length=50)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        if self.price is None or self.quantity is None:
            return 0
        return self.price * self.quantity

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def save(self, *args, **kwargs):
        # Sync the readable order_id to the item for easier cross-referencing
        self.crosscheck_id = self.order.order_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.title} (x{self.quantity})"


class OrderStatusHistory(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=250, choices=ORDER_STATUS)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['updated_at']

    def __str__(self):
        return f"{self.order.order_id} changed to {self.status}"