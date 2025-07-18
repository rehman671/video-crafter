# Generated by Django 4.2.20 on 2025-03-26 23:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processors', '0005_alter_video_output'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clips',
            name='srt_file',
            field=models.FileField(blank=True, null=True, upload_to='clip_srt_files/'),
        ),
        migrations.AlterField(
            model_name='clips',
            name='video_file',
            field=models.FileField(blank=True, null=True, upload_to='clips/'),
        ),
        migrations.AlterField(
            model_name='subclip',
            name='audio_file',
            field=models.FileField(blank=True, null=True, upload_to='audio_files/'),
        ),
        migrations.AlterField(
            model_name='subclip',
            name='srt_file',
            field=models.FileField(blank=True, null=True, upload_to='subclip_srt_files/'),
        ),
        migrations.AlterField(
            model_name='subclip',
            name='video_file',
            field=models.FileField(blank=True, null=True, upload_to='subclips/'),
        ),
    ]
