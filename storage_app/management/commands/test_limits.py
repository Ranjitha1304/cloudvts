# storage_app/management/commands/test_limits.py
from django.core.management.base import BaseCommand
from storage_app.models import StoragePlan

class Command(BaseCommand):
    help = 'Test storage and file size limits'
    
    def bytes_to_human_readable(self, bytes_value):
        """Convert bytes to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
    
    def handle(self, *args, **options):
        plans = StoragePlan.objects.all()
        
        for plan in plans:
            self.stdout.write(f"\n📊 Testing: {plan.name}")
            self.stdout.write(f"   Total Storage: {self.bytes_to_human_readable(plan.max_storage_size)}")
            self.stdout.write(f"   Max File Size: {self.bytes_to_human_readable(plan.max_file_size)}")
            
            # Test scenarios
            test_file_sizes = [
                plan.max_file_size - 1,  # Should pass
                plan.max_file_size,      # Should pass (exact limit)
                plan.max_file_size + 1,  # Should fail
            ]
            
            for test_size in test_file_sizes:
                if test_size <= plan.max_file_size:
                    status = "✅ PASS"
                else:
                    status = "❌ FAIL"
                
                self.stdout.write(f"   File size {self.bytes_to_human_readable(test_size)}: {status}")