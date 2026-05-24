# Generated migration to remove facility_name from Order model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0010_alter_order_facility_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='facility_name',
        ),
    ]
