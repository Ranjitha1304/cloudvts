# storage_app/apps.py
from django.apps import AppConfig

class StorageAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'storage_app'
    
    def ready(self):
        import storage_app.signals