import os
from django.db import migrations
from django.conf import settings

def populate_fonts(apps, schema_editor):
    # Get the Font model from the apps registry
    Font = apps.get_model('core', 'Font')
    
    # Define the fonts directory path
    fonts_dir = os.path.join(settings.BASE_DIR, 'fonts')
    
    # Check if the directory exists
    if not os.path.exists(fonts_dir):
        print(f"Warning: Fonts directory '{fonts_dir}' does not exist.")
        return
    
    # Font file extensions to look for
    font_extensions = ['.ttf', '.otf', '.woff', '.woff2']
    
    # Scan the directory for font files
    for file in os.listdir(fonts_dir):
        file_path = os.path.join(fonts_dir, file)
        
        # Check if it's a file and has a font extension
        if os.path.isfile(file_path) and any(file.lower().endswith(ext) for ext in font_extensions):
            # Create a readable name from the filename (without extension)
            name = os.path.splitext(file)[0].replace('_', ' ').replace('-', ' ').title()
            
            # Store the relative path to the font file
            relative_path = os.path.join('fonts', file)
            
            # Create a new Font instance
            Font.objects.create(
                name=name,
                font_path=relative_path
            )
            print(f"Added font: {name}")

def reverse_migration(apps, schema_editor):
    # Get the Font model
    Font = apps.get_model('core', 'Font')
    # Delete all font entries
    Font.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),  # Make sure to reference the correct previous migration
    ]

    operations = [
        migrations.RunPython(populate_fonts, reverse_migration),
    ]
