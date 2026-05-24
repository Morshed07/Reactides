from rest_framework import serializers
from django.db import transaction
from decimal import Decimal

from .models import Order, OrderItem, OrderStatusHistory
from apps.cart.models import Cart, Coupon
from apps.representative.models import Representative
from apps.account.models import ShippingAddress

SHIPPING_FEE = Decimal("25.00")


class OrderHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["status", "updated_at"]


class OrderItemSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "crosscheck_id",
            "product",
            "product_title",
            "quantity",
            "price",
            "dosage_strength",
            "dosage_unit",
            "total_price",
        ]


class OrderSerializer(serializers.ModelSerializer):
    orderitems = OrderItemSerializer(many=True, read_only=True)
    order_history = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_id",
            "contact_person",
            "email",
            "mobile_number",
            "address",
            "city",
            "state",
            "zip_code",
            "payment_method",
            "coupon_discount",
            "shipping_charge",
            "shipping_discount",
            "sub_total",
            "total",
            "tax_amount",
            "coupon_code",
            "shipping_coupon_code",
            "status",
            'created_at',
            'updated_at',
            "orderitems",
            "order_history",
            "representative_name",
            "representative_code"
        ]
        read_only_fields = (
            "order_id",
            "user",
            "sub_total",
            "total",
            "status",
            "paid",
            'created_at'
        )

    def get_order_history(self, obj):
        history = obj.status_history.all()
        return OrderHistorySerializer(history, many=True).data


class CheckoutSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = Order
        fields = [
            "contact_person",
            "email",
            "mobile_number",
            "address",
            "city",
            "state",
            "zip_code",
            "payment_method",
            "coupon_code",
            "coupon_discount",
        ]

    def validate_coupon_code(self, value):
        if not value:
            return value
        
        try:
            coupon = Coupon.objects.get(code=value, active=True)
            return value
        except Coupon.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive coupon code")

    def validate(self, attrs):
        user = self.context["request"].user

        try:
            cart = user.cart
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Cart not found")

        if cart.items.count() == 0:
            raise serializers.ValidationError("Cart is empty")

        if not cart.liability_waiver_accepted:
            raise serializers.ValidationError(
                "You must accept the liability waiver before checkout."
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        cart = user.cart
        coupon_code = validated_data.pop("coupon_code", None)

        # --------- CALCULATE FROM CART ---------
        subtotal = cart.subtotal
        coupon_discount = cart.coupon_discount
        tax = cart.tax_amount
        shipping_charge = SHIPPING_FEE
        shipping_discount = cart.shipping_discount
        total = (
            subtotal
            - coupon_discount
            + tax
            + shipping_charge
            - shipping_discount
        )

        # --------- SHIPPING COUPON CODE ---------
        shipping_coupon_code = None
        if cart.shipping_coupon:
            shipping_coupon_code = cart.shipping_coupon.code

        # --------- GET REPRESENTATIVE NAME & CODE ---------
        representative_name = None
        representative_code = None

        if user.representative_code:
            try:
                representative = Representative.objects.filter(
                    representative_code=user.representative_code
                ).first()

                if representative:
                    representative_name = representative.name
                    representative_code = (
                        representative.representative_code
                    )
            except Exception:
                pass

        # --------- CREATE ORDER ---------
        order = Order.objects.create(
            user=user,
            sub_total=subtotal,
            total=total,
            tax_amount=tax,
            coupon_discount=coupon_discount,
            coupon_code=coupon_code,
            shipping_charge=shipping_charge,
            shipping_discount=shipping_discount,
            shipping_coupon_code=shipping_coupon_code,
            representative_name=representative_name,
            representative_code=representative_code,
            **validated_data
        )

        # --------- CREATE SHIPPING ADDRESS ---------
        ShippingAddress.objects.create(
            user=user,
            contact_person=validated_data.get('contact_person'),
            email=validated_data.get('email'),
            address=validated_data.get('address'),
            city=validated_data.get('city'),
            state=validated_data.get('state'),
            zip_code=validated_data.get('zip_code'),
        )

        # --------- COPY CART ITEMS ---------
        for item in cart.items.select_related("product"):

            product = item.product

            # Optional stock check
            if product.quantity < item.product_quantity:
                raise serializers.ValidationError(
                    f"{product.title} is out of stock"
                )

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item.product_quantity,
                price=product.price,
                dosage_strength=product.dosage_strength,
                dosage_unit=product.dosage_unit,
            )

            # Deduct stock
            product.quantity -= item.product_quantity
            if product.quantity == 0:
                product.in_stock = False
            product.save()

        # --------- CLEAR CART ---------
        cart.items.all().delete()
        cart.coupon = None
        cart.shipping_coupon = None
        cart.liability_waiver_accepted = False
        cart.save()

        return order
