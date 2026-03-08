# Generated manually - SchoolSubscription for tracking subscription periods

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0022_set_default_plan_prices'),
    ]

    operations = [
        migrations.CreateModel(
            name='SchoolSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('payment_status', models.CharField(choices=[('paid', 'Paid'), ('pending', 'Pending'), ('expired', 'Expired')], default='pending', max_length=20)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='school_subscriptions', to='main_app.subscriptionplan')),
                ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscriptions', to='main_app.school')),
            ],
            options={
                'verbose_name': 'School Subscription',
                'verbose_name_plural': 'School Subscriptions',
                'ordering': ['-start_date'],
            },
        ),
    ]
