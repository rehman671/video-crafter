# Generated by Django 4.2.22 on 2025-06-09 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_font_css_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppVariables',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=100, unique=True)),
                ('value', models.TextField(blank=True, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'App Variables',
            },
        ),
    ]
