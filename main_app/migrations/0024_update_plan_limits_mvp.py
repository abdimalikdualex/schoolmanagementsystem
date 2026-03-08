# Update plan limits to match MVP spec: Starter 300, Standard 700, Premium Unlimited

from django.db import migrations


def update_plan_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    updates = {
        'Starter': {'student_limit': 300, 'teacher_limit': 15},
        'Standard': {'student_limit': 700, 'teacher_limit': 35},
        'Premium': {'student_limit': 0, 'teacher_limit': 0},  # 0 = Unlimited
    }
    for name, vals in updates.items():
        SubscriptionPlan.objects.filter(name=name).update(**vals)


def reverse_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model('main_app', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(name='Starter').update(student_limit=50, teacher_limit=10)
    SubscriptionPlan.objects.filter(name='Standard').update(student_limit=200, teacher_limit=30)
    SubscriptionPlan.objects.filter(name='Premium').update(student_limit=1000, teacher_limit=100)


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0023_schoolsubscription'),
    ]

    operations = [
        migrations.RunPython(update_plan_limits, reverse_limits),
    ]
