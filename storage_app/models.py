# storage_app/models.py
from django.db import models
from django.contrib.auth.models import User
import os
import uuid
from django.conf import settings
from django.utils import timezone

from django.core.exceptions import ValidationError

# Import the custom storage
try:
    from .storage_backends import BackblazeB2Storage
    cloud_storage = BackblazeB2Storage()
except ImportError:
    from storages.backends.s3boto3 import S3Boto3Storage
    cloud_storage = S3Boto3Storage(
        bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL
    )

def user_directory_path(instance, filename):
    return f'user_{instance.owner.id}/{filename}'

class StoragePlan(models.Model):
    PLAN_TYPES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('pro', 'Professional'),
        ('enterprise', 'Enterprise'),
    ]
    
    BILLING_PERIODS = [
        ('yearly', 'Yearly'),  
    ]
    
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES, default='free')
    max_storage_size = models.BigIntegerField()  # in bytes
    max_file_size = models.BigIntegerField(
        default=100 * 1024 * 1024,  # 100MB default
        help_text="Maximum allowed file size per upload in bytes"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_period = models.CharField(max_length=20, choices=BILLING_PERIODS, default='yearly')
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    features = models.JSONField(default=list)
    display_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['display_order', 'price']
    
    def __str__(self):
        return f"{self.name} (₹{self.price}/year)"
    
    def get_yearly_price(self):
        """Get price in rupees for yearly billing"""
        return f"₹{self.price}/year"
    
    def get_monthly_equivalent(self):
        """Calculate monthly equivalent for display"""
        monthly = float(self.price) / 12
        return f"₹{monthly:.2f}/month"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    storage_plan = models.ForeignKey(StoragePlan, on_delete=models.SET_NULL, null=True)
    used_storage = models.BigIntegerField(default=0)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    
    def get_storage_usage_percent(self):
        if self.storage_plan:
            return (self.used_storage / self.storage_plan.max_storage_size) * 100
        return 0
    
    def can_upload_file(self, file_size):
        """Check if user can upload file based on their plan and storage"""
        if not self.storage_plan:
            return False
        
        if (self.used_storage + file_size) > self.storage_plan.max_storage_size:
            return False
        
        return True
    
    def __str__(self):
        return f"{self.user.username}'s profile"

class Subscription(models.Model):
    SUBSCRIPTION_STATUS = [
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('past_due', 'Past Due'),
        ('unpaid', 'Unpaid'),
        ('incomplete', 'Incomplete'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(StoragePlan, on_delete=models.CASCADE)
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS, default='incomplete')
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def is_active(self):
        return self.status == 'active' and not self.cancel_at_period_end
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"

class Folder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    parent_folder = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subfolders')
    created_at = models.DateTimeField(auto_now_add=True)
    is_starred = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)  
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['name', 'owner', 'parent_folder']
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_full_path(self):
        """Get the full folder path"""
        if self.parent_folder:
            return f"{self.parent_folder.get_full_path()}/{self.name}"
        return self.name
    
    def get_files_count(self):
        """Count files in this folder"""
        return self.files.filter(is_deleted=False).count()
    
    def get_subfolders_count(self):
        """Count subfolders"""
        return self.subfolders.filter(is_deleted=False).count()
    
    def toggle_star(self):
        """Toggle star status"""
        self.is_starred = not self.is_starred
        self.save()
        return self.is_starred
    
    def toggle_visibility(self):
        """Toggle public/private status"""
        self.is_public = not self.is_public
        self.save()
        return self.is_public
    
    def soft_delete(self):
        """Soft delete folder and all its contents"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()
        
        
        # Soft delete all files in this folder
        self.files.filter(is_deleted=False).update(
            is_deleted=True, 
            deleted_at=timezone.now()
        )
        
        # Recursively soft delete subfolders
        for subfolder in self.subfolders.filter(is_deleted=False):
            subfolder.soft_delete()

        

    def restore(self):
        """Restore folder and all its contents"""
        self.is_deleted = False
        self.deleted_at = None
        self.save()
        
        # Restore all files in this folder
        self.files.filter(is_deleted=True).update(
            is_deleted=False, 
            deleted_at=None
        )
        
        # Recursively restore subfolders
        for subfolder in self.subfolders.filter(is_deleted=True):
            subfolder.restore()
            
    
    # NEW METHOD ADDED FOR PASSWORD PROTECTION
    def can_require_password(self):
        """Only private folders can require password protection"""
        return not self.is_public
    
    def get_share_link(self):
        """Get active share link for this folder"""
        return ShareLink.objects.filter(folder=self, is_active=True).first()

class Trash(models.Model):
    """Model to track files and folders in trash"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.ForeignKey('File', on_delete=models.CASCADE, null=True, blank=True)
    folder = models.ForeignKey('Folder', on_delete=models.CASCADE, null=True, blank=True)
    original_folder = models.ForeignKey('Folder', on_delete=models.SET_NULL, null=True, blank=True, related_name='trash_items')
    deleted_at = models.DateTimeField(auto_now_add=True)
    scheduled_permanent_deletion = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-deleted_at']
    
    def __str__(self):
        if self.file:
            return f"Trash item: {self.file.name}"
        elif self.folder:
            return f"Trash item: Folder {self.folder.name}"
        return "Invalid trash item"
    
    def clean(self):
        if not self.file and not self.folder:
            raise ValidationError("Trash item must be associated with either a file or a folder.")
        if self.file and self.folder:
            raise ValidationError("Trash item cannot be associated with both a file and a folder.")
        
        
class File(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    file = models.FileField(
        upload_to=user_directory_path,
        storage=cloud_storage
    )
    file_type = models.CharField(max_length=50)
    size = models.BigIntegerField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='files')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if not self.name:
            self.name = os.path.basename(self.file.name)
        if not self.file_type:
            self.file_type = os.path.splitext(self.file.name)[1].lower()
        super().save(*args, **kwargs)

    def soft_delete(self):
        """Soft delete - move to trash"""
        self.is_deleted = True
        self.save()
    
    def restore(self):
        """Restore from trash"""
        self.is_deleted = False
        self.save()    
    
    def __str__(self):
        return self.name
    
    # NEW METHOD ADDED FOR PASSWORD PROTECTION
    def can_require_password(self):
        """Only private files can require password protection"""
        return not self.is_public
    
    def get_share_link(self):
        """Get active share link for this file"""
        return ShareLink.objects.filter(file=self, is_active=True).first()

class ShareLink(models.Model):
    file = models.ForeignKey(File, on_delete=models.CASCADE, null=True, blank=True)
    folder = models.ForeignKey('Folder', on_delete=models.CASCADE, null=True, blank=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Add password protection fields
    require_password = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        if self.file:
            return f"Share link for {self.file.name}"
        elif self.folder:
            return f"Share link for folder {self.folder.name}"
        return "Invalid share link"
    
    def clean(self):
        if not self.file and not self.folder:
            raise ValidationError("Share link must be associated with either a file or a folder.")
        if self.file and self.folder:
            raise ValidationError("Share link cannot be associated with both a file and a folder.")
    
    def set_password(self, password):
        """Hash and set the password"""
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(password)
        self.require_password = True
        self.save()
    
    def check_password(self, password):
        """Verify the password"""
        from django.contrib.auth.hashers import check_password
        if not self.password_hash:
            return False
        return check_password(password, self.password_hash)
    
    def has_password(self):
        """Check if this share link has password protection"""
        return self.require_password and bool(self.password_hash)