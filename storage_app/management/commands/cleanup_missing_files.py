# storage_app/management/commands/cleanup_missing_files.py
from django.core.management.base import BaseCommand
from storage_app.models import File
from django.core.files.storage import default_storage

class Command(BaseCommand):
    help = 'Clean up database records for files missing in storage'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete the missing file records',
        )
    
    def handle(self, *args, **options):
        files = File.objects.all()
        delete_mode = options['delete']
        
        self.stdout.write("🔍 Checking files in storage...")
        
        missing_count = 0
        for file in files:
            exists = default_storage.exists(file.file.name)
            if not exists:
                missing_count += 1
                self.stdout.write(f"❌ MISSING - {file.file.name} (ID: {file.id})")
                
                if delete_mode:
                    file.delete()
                    self.stdout.write(f"🗑️ DELETED - {file.file.name}")
        
        self.stdout.write(f"\n📊 Summary: {missing_count} missing files found")
        
        if not delete_mode and missing_count > 0:
            self.stdout.write("\n💡 Run with --delete to remove these records")