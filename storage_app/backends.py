from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q

class CaseInsensitiveAuthBackend(ModelBackend):
    """Custom authentication backend for case-insensitive login"""
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Try to find user by username (case-insensitive) or email
            user = User.objects.get(
                Q(username__iexact=username) | 
                Q(email__iexact=username)
            )
            
            # Check password and return user if valid
            if user.check_password(password):
                return user
                
        except User.DoesNotExist:
            # No user found with this username/email
            return None
        except User.MultipleObjectsReturned:
            # Multiple users found (shouldn't happen with proper validation)
            return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None