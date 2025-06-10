from django.db import migrations
from django.conf import settings

def create_app_variable(apps, schema_editor):
    AppVariable = apps.get_model('core', 'AppVariables')
    AppVariable.objects.create(
        key='ELEVENLABS_ALIGNMENT_KEY',
        value=settings.ELEVENLABS_ALIGNMENT_KEY if hasattr(settings, 'ELEVENLABS_ALIGNMENT_KEY') else '',
        description='Default key added by migration'
    )

def reverse_app_variable(apps, schema_editor):
    AppVariable = apps.get_model('core', 'AppVariables')
    AppVariable.objects.filter(key='ELEVENLABS_ALIGNMENT_KEY').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0008_appvariables'),  # Update this to your previous migration
    ]

    operations = [
        migrations.RunPython(create_app_variable, reverse_app_variable),
    ]