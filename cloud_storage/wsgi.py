import os
import django
from django.core.management import call_command
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_storage.settings')
django.setup()

try:
    call_command("migrate", interactive=False)
except Exception as e:
    print(f"Migration error: {e}")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
