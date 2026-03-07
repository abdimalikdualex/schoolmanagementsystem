# Generated manually for multi-tenant School model

from django.db import migrations, models
import django.db.models.deletion


def create_default_school_and_assign(apps, schema_editor):
    """Create default school and assign all existing records to it."""
    School = apps.get_model('main_app', 'School')
    CustomUser = apps.get_model('main_app', 'CustomUser')
    SchoolSettings = apps.get_model('main_app', 'SchoolSettings')
    Session = apps.get_model('main_app', 'Session')
    AcademicTerm = apps.get_model('main_app', 'AcademicTerm')
    GradeLevel = apps.get_model('main_app', 'GradeLevel')
    Stream = apps.get_model('main_app', 'Stream')
    SchoolClass = apps.get_model('main_app', 'SchoolClass')
    AdmissionSetting = apps.get_model('main_app', 'AdmissionSetting')

    # Create default school
    default_school, _ = School.objects.get_or_create(
        code='DEFAULT',
        defaults={
            'name': 'Default School',
            'email': '',
            'phone': '',
            'address': '',
            'is_active': True,
        }
    )

    # Assign users (except superusers - they stay school=None for Super Admin)
    CustomUser.objects.filter(school__isnull=True).exclude(is_superuser=True).update(school=default_school)

    # Assign SchoolSettings
    SchoolSettings.objects.filter(school__isnull=True).update(school=default_school)

    # Assign Sessions, AcademicTerms, GradeLevels, Streams, SchoolClasses, AdmissionSettings
    Session.objects.filter(school__isnull=True).update(school=default_school)
    AcademicTerm.objects.filter(school__isnull=True).update(school=default_school)
    GradeLevel.objects.filter(school__isnull=True).update(school=default_school)
    Stream.objects.filter(school__isnull=True).update(school=default_school)
    SchoolClass.objects.filter(school__isnull=True).update(school=default_school)
    AdmissionSetting.objects.filter(school__isnull=True).update(school=default_school)


def reverse_migration(apps, schema_editor):
    """Reverse: set all school FKs back to null."""
    CustomUser = apps.get_model('main_app', 'CustomUser')
    SchoolSettings = apps.get_model('main_app', 'SchoolSettings')
    Session = apps.get_model('main_app', 'Session')
    AcademicTerm = apps.get_model('main_app', 'AcademicTerm')
    GradeLevel = apps.get_model('main_app', 'GradeLevel')
    Stream = apps.get_model('main_app', 'Stream')
    SchoolClass = apps.get_model('main_app', 'SchoolClass')
    AdmissionSetting = apps.get_model('main_app', 'AdmissionSetting')

    CustomUser.objects.all().update(school=None)
    SchoolSettings.objects.all().update(school=None)
    Session.objects.all().update(school=None)
    AcademicTerm.objects.all().update(school=None)
    GradeLevel.objects.all().update(school=None)
    Stream.objects.all().update(school=None)
    SchoolClass.objects.all().update(school=None)
    AdmissionSetting.objects.all().update(school=None)


class Migration(migrations.Migration):

    dependencies = [
        ('main_app', '0015_add_fee_due_date_and_payment_schedule'),
    ]

    operations = [
        migrations.CreateModel(
            name='School',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('code', models.CharField(help_text='Unique code e.g., SCH001, used for subdomain', max_length=20, unique=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='schools/')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'School',
                'verbose_name_plural': 'Schools',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='customuser',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for Super Admin; required for all other roles',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='users',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='schoolsettings',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null = legacy single-school; one settings per school for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='settings',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='session',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; required for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='sessions',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='academicterm',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; required for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='academic_terms',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='gradelevel',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; required for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='grade_levels',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='stream',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; required for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='streams',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='schoolclass',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; required for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='classes',
                to='main_app.school'
            ),
        ),
        migrations.AddField(
            model_name='admissionsetting',
            name='school',
            field=models.ForeignKey(
                blank=True,
                help_text='Null for legacy data; one per school for multi-tenant',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='admission_settings',
                to='main_app.school'
            ),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='user_type',
            field=models.CharField(
                choices=[
                    (0, 'Super Admin'),
                    (1, 'HOD'),
                    (2, 'Staff'),
                    (3, 'Student'),
                    (4, 'Parent'),
                    (5, 'Finance Officer'),
                ],
                default=1,
                max_length=1
            ),
        ),
        migrations.RunPython(create_default_school_and_assign, reverse_migration),
    ]
