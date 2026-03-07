# Generated manually - create default subscription plans

from django.db import migrations


def create_default_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    plans = [
        {'name': 'Starter', 'student_limit': 50, 'teacher_limit': 10, 'description': 'For small schools'},
        {'name': 'Standard', 'student_limit': 200, 'teacher_limit': 30, 'description': 'For medium schools'},
        {'name': 'Premium', 'student_limit': 1000, 'teacher_limit': 100, 'description': 'For large schools'},
    ]
    for p in plans:
        SubscriptionPlan.objects.get_or_create(name=p['name'], defaults=p)


def reverse_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(name__in=['Starter', 'Standard', 'Premium']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0018_add_subscription_plan'),
    ]

    operations = [
        migrations.RunPython(create_default_plans, reverse_plans),
    ]
