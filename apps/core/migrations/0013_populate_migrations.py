from django.db import migrations


def add_ffmpeg_transitions(apps, schema_editor):
    Transition = apps.get_model('core', 'Transitions')  # Adjust if your app is not 'core'

    transitions = {
        "circleclose": "Circle Close",
        "circleopen": "Circle Open",
        "diagbl": "Diagonal Bottom Left",
        "diagbr": "Diagonal Bottom Right",
        "diagtl": "Diagonal Top Left",
        "diagtr": "Diagonal Top Right",
        "fade": "Fade",
        "fadeblack": "Fade to Black",
        "fadewhite": "Fade to White",
        "hblur": "Horizontal Blur",
        "hlwind": "Horizontal Left Wind",
        "horzclose": "Horizontal Close",
        "horzopen": "Horizontal Open",
        "hrwind": "Horizontal Right Wind",
        "smoothdown": "Smooth Down",
        "smoothleft": "Smooth Left",
        "smoothright": "Smooth Right",
        "smoothup": "Smooth Up",
        "vdwind": "Vertical Down Wind",
        "vertclose": "Vertical Close",
        "vertopen": "Vertical Open",
        "vuwind": "Vertical Up Wind",
        # "zoomin": "Zoom In",  # Excluded for FFmpeg < 5.1
    }

    created = 0
    for slug, name in transitions.items():
        if not Transition.objects.filter(slug=slug).exists():
            Transition.objects.create(name=name, slug=slug)
            created += 1

    print(f"[Migration] Added {created} transitions.")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_alter_transitions_duration'),  # Change if needed
    ]

    operations = [
        migrations.RunPython(add_ffmpeg_transitions),
    ]
