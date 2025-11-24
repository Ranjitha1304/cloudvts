# storage_app/management/commands/check_files.py
from django.core.management.base import BaseCommand
from storage_app.models import File
from django.core.files.storage import default_storage

class Command(BaseCommand):
    help = 'Check if files exist in storage'
    
    def handle(self, *args, **options):
        files = File.objects.all()
        
        for file in files:
            exists = default_storage.exists(file.file.name)
            status = "✅ EXISTS" if exists else "❌ MISSING"
            self.stdout.write(f"{status} - {file.file.name} (ID: {file.id})")