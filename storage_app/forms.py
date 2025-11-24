# storage_app/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import File, Folder, ShareLink, StoragePlan
import stripe
from django.conf import settings

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    plan_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
    
    def clean_username(self):
        username = self.cleaned_data['username']
        # Case-insensitive username check
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username.lower()
    
    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with that email already exists.")
        return email
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = self.cleaned_data['username'].lower()
        if commit:
            user.save()
        return user        

class FileUploadForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ['file', 'is_public']
        widgets = {
            'file': forms.FileInput(attrs={
                'accept': '*/*'  # Allow all file types
            })
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        # size validation handled in the view based on user's plan
        return file
    

class FileShareForm(forms.Form):
    expires_in = forms.ChoiceField(
        choices=[
            (1, "1 day"),
            (7, "1 week"),
            (30, "1 month"),
            (None, "Never")
        ],
        required=False
    )

class FolderCreateForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Enter folder name'
            })
        }

class MoveFileForm(forms.Form):
    folder = forms.ModelChoiceField(
        queryset=Folder.objects.none(),
        required=False,
        empty_label="Root (No Folder)",
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500'
        })
    )
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['folder'].queryset = Folder.objects.filter(owner=user).order_by('name')

class StoragePlanForm(forms.ModelForm):
    """Form for creating/editing storage plans"""
    features = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Enter features separated by commas or new lines\nExample: 5GB Storage, Basic Support, File Sharing'
        }),
        help_text="Enter features separated by commas or new lines"
    )
    
    # Custom field for human-readable storage input
    max_storage_size_input = forms.CharField(
        label="Total Storage Size",
        max_length=20,
        help_text="Total storage capacity (e.g., 5GB, 50GB, 1TB, 500MB)",
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., 5GB, 1TB, 500MB'
        })
    )
    
    # ADD: Custom field for file size limit
    max_file_size_input = forms.CharField(
        label="Max File Size",
        max_length=20,
        help_text="Maximum file size per upload (e.g., 100MB, 2GB, 5GB)",
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g., 100MB, 2GB, 5GB'
        })
    )
    
    class Meta:
        model = StoragePlan
        # REMOVED: 'stripe_price_id' from fields - we'll handle it automatically
        # REMOVED: 'max_storage_size' and 'max_file_size' - using custom fields
        fields = [
            'name', 'plan_type', 'price', 
            'billing_period', 'is_active', 
            'features', 'display_order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'plan_type': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'billing_period': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If editing, convert existing bytes to human-readable format
        if self.instance and self.instance.pk:
            # Convert total storage size
            storage_bytes = self.instance.max_storage_size
            if storage_bytes >= 1024**4:  # 1TB
                human_readable = f"{storage_bytes / (1024**4):.0f}TB"
            elif storage_bytes >= 1024**3:  # 1GB
                human_readable = f"{storage_bytes / (1024**3):.0f}GB"
            elif storage_bytes >= 1024**2:  # 1MB
                human_readable = f"{storage_bytes / (1024**2):.0f}MB"
            else:
                human_readable = f"{storage_bytes} bytes"
            
            self.initial['max_storage_size_input'] = human_readable
            
            # Convert file size limit
            file_size_bytes = self.instance.max_file_size
            if file_size_bytes >= 1024**3:  # 1GB
                file_size_readable = f"{file_size_bytes / (1024**3):.0f}GB"
            elif file_size_bytes >= 1024**2:  # 1MB
                file_size_readable = f"{file_size_bytes / (1024**2):.0f}MB"
            else:
                file_size_readable = f"{file_size_bytes} bytes"
            
            self.initial['max_file_size_input'] = file_size_readable
    
    def clean_max_storage_size_input(self):
        """Convert human-readable storage input to bytes"""
        storage_input = self.cleaned_data.get('max_storage_size_input', '').upper().strip()
        
        if not storage_input:
            raise forms.ValidationError("Total storage size is required")
        
        # Remove any spaces and convert to uppercase
        storage_input = storage_input.replace(' ', '').upper()
        
        # Define conversion factors
        units = {
            'KB': 1024,
            'MB': 1024**2,
            'GB': 1024**3, 
            'TB': 1024**4,
        }
        
        # Try to extract number and unit
        import re
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGTP]?B)?$', storage_input)
        
        if not match:
            raise forms.ValidationError(
                "Please enter a valid storage size (e.g., 5GB, 50GB, 1TB, 500MB)"
            )
        
        number = float(match.group(1))
        unit = match.group(2) or 'B'  # Default to bytes if no unit
        
        if unit == 'B':
            return int(number)
        elif unit in units:
            return int(number * units[unit])
        else:
            raise forms.ValidationError(
                f"Unknown unit: {unit}. Use MB, GB, or TB"
            )
    
    def clean_max_file_size_input(self):
        """Convert human-readable file size input to bytes"""
        file_size_input = self.cleaned_data.get('max_file_size_input', '').upper().strip()
        
        if not file_size_input:
            raise forms.ValidationError("Max file size is required")
        
        # Remove any spaces and convert to uppercase
        file_size_input = file_size_input.replace(' ', '').upper()
        
        # Define conversion factors
        units = {
            'KB': 1024,
            'MB': 1024**2,
            'GB': 1024**3, 
            'TB': 1024**4,
        }
        
        # Try to extract number and unit
        import re
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGTP]?B)?$', file_size_input)
        
        if not match:
            raise forms.ValidationError(
                "Please enter a valid file size (e.g., 100MB, 2GB, 5GB)"
            )
        
        number = float(match.group(1))
        unit = match.group(2) or 'B'  # Default to bytes if no unit
        
        if unit == 'B':
            return int(number)
        elif unit in units:
            return int(number * units[unit])
        else:
            raise forms.ValidationError(
                f"Unknown unit: {unit}. Use MB or GB"
            )
    
    def clean_features(self):
        """Convert features string to list"""
        features = self.cleaned_data.get('features', '')
        # Split by commas or new lines and strip whitespace
        features_list = [feature.strip() for feature in features.replace('\n', ',').split(',') if feature.strip()]
        return features_list
    
    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        
        # If it's a paid plan, ensure we have Stripe credentials
        if price and float(price) > 0:
            if not settings.STRIPE_SECRET_KEY:
                raise forms.ValidationError(
                    "Stripe is not configured. Please contact system administrator."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        # Get the converted storage size from our custom field
        storage_bytes = self.cleaned_data.get('max_storage_size_input')
        
        # Get the converted file size from our custom field
        file_size_bytes = self.cleaned_data.get('max_file_size_input')
        
        # Create instance but don't save yet
        instance = super().save(commit=False)
        
        # Set the storage size in bytes
        instance.max_storage_size = storage_bytes
        
        # Set the file size limit in bytes
        instance.max_file_size = file_size_bytes
        
        # Auto-create Stripe product for paid plans (price > 0)
        price = float(instance.price) if instance.price else 0
        is_paid_plan = price > 0
        
        if is_paid_plan and not instance.stripe_price_id:
            try:
                # Create product in Stripe
                product = stripe.Product.create(
                    name=instance.name,
                    description=f"{instance.name} - Cloud Storage Plan",
                    metadata={
                        'plan_type': instance.plan_type,
                        'storage_gb': storage_bytes / (1024**3),
                        'max_file_size_gb': file_size_bytes / (1024**3),
                        'features': ', '.join(instance.features) if instance.features else ''
                    }
                )
                
                # Create price in Stripe (convert to paise for INR)
                price_data = {
                    'product': product.id,
                    'unit_amount': int(price * 100),  # Convert rupees to paise
                    'currency': 'inr',
                }
                
                # Add recurring billing for yearly plans
                if instance.billing_period == 'yearly':
                    price_data['recurring'] = {'interval': 'year'}
                else:
                    price_data['recurring'] = {'interval': 'month'}
                
                price_obj = stripe.Price.create(**price_data)
                
                # Set the Stripe price ID
                instance.stripe_price_id = price_obj.id
                
                print(f"✅ Successfully created Stripe product: {instance.name}")
                print(f"✅ Stripe Price ID: {instance.stripe_price_id}")
                
            except stripe.error.StripeError as e:
                # Log the error but don't prevent saving
                print(f"❌ Stripe error creating product for {instance.name}: {e}")
                # You could also set a flag or send a notification
            except Exception as e:
                print(f"❌ Unexpected error creating Stripe product: {e}")
        
        elif not is_paid_plan:
            # For free plans, ensure stripe_price_id is empty
            instance.stripe_price_id = None
        
        if commit:
            instance.save()
        
        return instance    