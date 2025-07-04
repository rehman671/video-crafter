# Generated by Django 4.2.22 on 2025-06-23 21:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processors', '0036_subclip_is_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='subclip',
            name='asset_folder',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='subclip',
            name='asset_key',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='subclip',
            name='is_asset',
            field=models.BooleanField(default=False),
        ),
    ]
