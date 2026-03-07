# School approval workflow - status field

from django.db import migrations, models


def set_existing_schools_approved(apps, schema_editor):
    """Existing schools should be approved so they continue working."""
    School = apps.get_model('main_app', 'School')
    School.objects.all().update(status='approved')


def reverse_migration(apps, schema_editor):
    pass  # No reverse needed for data


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0016_add_multi_tenant_school'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Approval'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('suspended', 'Suspended'),
                ],
                default='pending',
                help_text='Only approved schools can access the system',
                max_length=20
            ),
        ),
        migrations.RunPython(set_existing_schools_approved, reverse_migration),
    ]
