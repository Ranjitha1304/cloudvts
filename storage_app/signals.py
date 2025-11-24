# storage_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, StoragePlan

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create UserProfile when User is created"""
    if created:
        try:
            # Check if profile already exists (shouldn't, but just in case)
            if not hasattr(instance, 'userprofile'):
                # Get free plan or create one if it doesn't exist
                free_plan, _ = StoragePlan.objects.get_or_create(
                    plan_type='free',
                    defaults={
                        'name': 'Free Plan',
                        'max_storage_size': 5 * 1024 * 1024 * 1024,  # 5GB
                        'price': 0,
                        'billing_period': 'yearly',
                        'is_active': True,
                        'features': ['5GB Storage', 'Basic Support', 'File Sharing'],
                        'display_order': 0
                    }
                )
                UserProfile.objects.create(user=instance, storage_plan=free_plan)
        except Exception as e:
            print(f"Error creating user profile: {e}")

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    try:
        instance.userprofile.save()
    except UserProfile.DoesNotExist:
        # If profile doesn't exist, create it
        create_user_profile(sender, instance, True, **kwargs)