# storage_app/storage_backends.py
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class BackblazeB2Storage(S3Boto3Storage):
    def __init__(self, *args, **kwargs):
        kwargs['bucket_name'] = settings.AWS_STORAGE_BUCKET_NAME
        kwargs['endpoint_url'] = settings.AWS_S3_ENDPOINT_URL
        kwargs['access_key'] = settings.AWS_ACCESS_KEY_ID
        kwargs['secret_key'] = settings.AWS_SECRET_ACCESS_KEY
        kwargs['file_overwrite'] = False
        kwargs['default_acl'] = 'private'
        kwargs['querystring_auth'] = True
        kwargs['location'] = 'media'
        super().__init__(*args, **kwargs)
    
    def get_available_name(self, name, max_length=None):
        # Use the original filename without modification
        return name
    
    def _save(self, name, content):
        # Normalize path separators for Backblaze
        name = name.replace('\\', '/')
        # Save with the exact name provided
        print(f"💾 Storage saving file: {name}")
        saved_name = super()._save(name, content)
        print(f"💾 Storage saved as: {saved_name}")
        return saved_name
    
    def url(self, name):
        # Normalize path for URL generation
        name = name.replace('\\', '/')
        # Generate proper URL for Backblaze B2
        url = super().url(name)
        print(f"🔗 Storage URL generated for {name}: {url}")
        return url