# Backfill payment_method: картой онлайн / СБП → банковской картой при получении

from django.db import migrations


def backfill_online_sbp_to_card(apps, schema_editor):
    Order = apps.get_model('core', 'Order')
    Order.objects.filter(payment_method__in=('card_online', 'sbp')).update(
        payment_method='card_on_hand'
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_order_payment_method_order_pickup_cost_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_online_sbp_to_card, noop),
    ]
