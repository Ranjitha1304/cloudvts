# storage_app/management/commands/create_default_plans.py
from django.core.management.base import BaseCommand
from storage_app.models import StoragePlan

class Command(BaseCommand):
    help = 'Create default storage plans'
    
    def handle(self, *args, **options):
        plans_data = [
            {
                'name': 'Free Plan',
                'plan_type': 'free',
                'max_storage_size': 5 * 1024 * 1024 * 1024,  # 5GB
                'max_file_size': 100 * 1024 * 1024,  # 100MB file limit
                'price': 0,
                'billing_period': 'yearly',
                'is_active': True,
                'features': ['5GB Storage', 'Basic Support', 'File Sharing'],
                'display_order': 0
            },
            {
                'name': 'Basic Plan',
                'plan_type': 'basic',
                'max_storage_size': 50 * 1024 * 1024 * 1024,  # 50GB
                'max_file_size': 2 * 1024 * 1024 * 1024,  # 2GB file limit
                'price': 999,
                'billing_period': 'yearly',
                'is_active': True,
                'features': ['50GB Storage', 'Priority Support', 'Advanced Sharing'],
                'display_order': 1
            },
            {
                'name': 'Professional Plan',
                'plan_type': 'pro',
                'max_storage_size': 200 * 1024 * 1024 * 1024,  # 200GB
                'max_file_size': 5 * 1024 * 1024 * 1024,  # 5GB file limit
                'price': 1999,
                'billing_period': 'yearly',
                'is_active': True,
                'features': ['200GB Storage', '24/7 Support', 'Advanced Analytics'],
                'display_order': 2
            },
            # {
            #     'name': 'Enterprise Plan',
            #     'plan_type': 'enterprise',
            #     'max_storage_size': 1024 * 1024 * 1024 * 1024,  # 1TB
            #     'price': 4999,
            #     'billing_period': 'yearly',
            #     'is_active': True,
            #     'features': ['1TB Storage', 'Dedicated Support', 'Team Collaboration'],
            #     'display_order': 3
            # }
        ]
        
        for plan_data in plans_data:
            plan, created = StoragePlan.objects.get_or_create(
                plan_type=plan_data['plan_type'],
                defaults=plan_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created {plan_data["name"]}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'{plan_data["name"]} already exists')
                )