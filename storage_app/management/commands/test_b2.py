# storage_app/management/commands/test_b2.py
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.conf import settings
import boto3
from botocore.client import Config

class Command(BaseCommand):
    help = 'Test Backblaze B2 connection'
    
    def handle(self, *args, **options):
        self.stdout.write("🔧 Testing Backblaze B2 connection...")
        
        try:
            # Test using boto3 directly
            s3_client = boto3.client(
                's3',
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                config=Config(signature_version='s3v4')
            )
            
            # List buckets to test connection
            response = s3_client.list_buckets()
            self.stdout.write("✅ Successfully connected to Backblaze B2")
            self.stdout.write(f"📦 Available buckets: {[b['Name'] for b in response['Buckets']]}")
            
            # Check if our bucket exists
            buckets = [b['Name'] for b in response['Buckets']]
            if settings.AWS_STORAGE_BUCKET_NAME in buckets:
                self.stdout.write(f"✅ Bucket '{settings.AWS_STORAGE_BUCKET_NAME}' exists")
            else:
                self.stdout.write(f"❌ Bucket '{settings.AWS_STORAGE_BUCKET_NAME}' not found")
                
        except Exception as e:
            self.stdout.write(f"❌ Connection failed: {e}")