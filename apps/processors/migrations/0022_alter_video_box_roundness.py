# Generated by Django 4.2.20 on 2025-04-20 23:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processors', '0021_video_output_with_bg'),
    ]

    operations = [
        migrations.AlterField(
            model_name='video',
            name='box_roundness',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
