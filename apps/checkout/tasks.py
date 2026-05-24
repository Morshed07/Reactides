import logging
from datetime import datetime

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from apps.checkout.models import Order
from apps.notification.models import Alert

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_email(self, order_id):
    try:
        order = Order.objects.select_related('user').prefetch_related(
            'orderitems__product'
        ).get(order_id=order_id)
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found. Cannot send confirmation email.")
        return

    # Build order items context
    items = []
    for item in order.orderitems.all():
        items.append({
            'product_title': item.product.title,
            'quantity': item.quantity,
            'price': f"{item.price:.2f}",
            'total_price': f"{item.total_price:.2f}",
            'dosage_strength': item.dosage_strength,
            'dosage_unit': item.dosage_unit,
        })

    # Build email context
    context = {
        'order_id': order.order_id,
        'contact_person': order.contact_person,
        'email': order.email,
        'payment_method': order.get_payment_method_display(),
        'status': order.status,
        'items': items,
        'sub_total': f"{order.sub_total:.2f}",
        'coupon_discount': f"{order.coupon_discount:.2f}" if order.coupon_discount else None,
        'tax_amount': f"{order.tax_amount:.2f}",
        'shipping_charge': f"{order.shipping_charge:.2f}",
        'total': f"{order.total:.2f}",
        'address': order.address,
        'city': order.city,
        'state': order.state,
        'zip_code': order.zip_code,
        'year': datetime.now().year,
    }

    try:
        # Render HTML email
        html_content = render_to_string(
            'checkout/order_confirmation_email.html', context
        )
        text_content = strip_tags(html_content)

        subject = f"Order Confirmation - {order.order_id}"
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [order.email]

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipient_list,
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        logger.info(
            f"Order confirmation email sent successfully for {order.order_id} "
            f"to {order.email}"
        )

    except Exception as exc:
        logger.error(
            f"Failed to send order confirmation email for {order.order_id}: {exc}"
        )
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_admin_order_notification_email(self):
    try:
        alert_emails = list(Alert.objects.values_list('admin_email', flat=True))
        if not alert_emails:
            logger.warning("No admin alert emails configured. Skipping admin notification.")
            return

        # Render HTML email
        html_content = render_to_string(
            'checkout/admin_order_notification_email.html'
        )
        text_content = strip_tags(html_content)

        subject = f"New Order Notification"
        from_email = settings.DEFAULT_FROM_EMAIL

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=alert_emails,
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        logger.info(
            f"Admin order notification email sent successfully "
            f"to {alert_emails}"
        )

    except Exception as exc:
        logger.error(
            f"Failed to send admin notification email: {exc}"
        )
        raise self.retry(exc=exc)