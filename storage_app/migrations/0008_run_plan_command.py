from django.db import migrations
from django.core.management import call_command

def load_plans(apps, schema_editor):
    try:
        call_command("create_default_plans")
    except Exception as e:
        print("Error loading default plans:", e)

class Migration(migrations.Migration):

    dependencies = [
        ('storage_app', '0007_storageplan_max_file_size'),
    ]

    operations = [
        migrations.RunPython(load_plans),
    ]
