# Set default monthly prices for subscription plans (MVP)

from decimal import Decimal
from django.db import migrations


def set_plan_prices(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    prices = {
        'Starter': Decimal('15.00'),
        'Standard': Decimal('30.00'),
        'Premium': Decimal('60.00'),
    }
    for name, price in prices.items():
        SubscriptionPlan.objects.filter(name=name).update(monthly_price=price)


def reverse_prices(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(name__in=['Starter', 'Standard', 'Premium']).update(monthly_price=0)


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0021_email_verification_and_subscription_price'),
    ]

    operations = [
        migrations.RunPython(set_plan_prices, reverse_prices),
    ]
