from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
import random
import string

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    
    def pre_social_login(self, request, sociallogin):
        """
        Connect social account to existing user with same email
        Handles multiple users with same email
        """
        # If user already has an account, connect the social account
        if sociallogin.is_existing:
            return

        try:
            # Check if users with this email exist
            if sociallogin.user.email:
                existing_users = User.objects.filter(email=sociallogin.user.email)
                
                if existing_users.exists():
                    # Use the most recent user
                    existing_user = existing_users.latest('date_joined')
                    
                    # Connect the social account to the existing user
                    sociallogin.connect(request, existing_user)
                    
                    # Add a success message
                    messages.success(request, "Your Google account has been connected to your existing account!")
                    
        except User.DoesNotExist:
            # User doesn't exist, let allauth create it
            pass

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Allow auto signup for social logins
        """
        return True

    def save_user(self, request, sociallogin, form=None):
        """
        Ensure proper user creation with unique username
        """
        user = super().save_user(request, sociallogin, form)
        
        # Generate unique username if not provided or if it conflicts
        if not user.username or User.objects.filter(username=user.username).exclude(id=user.id).exists():
            user.username = self.generate_unique_username(user.email)
            user.save()
        
        return user

    def generate_unique_username(self, email):
        """
        Generate a unique username from email
        """
        base_username = email.split('@')[0]
        username = base_username
        
        # If username exists, append random numbers
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
            if counter > 100:  # Safety limit
                username = f"{base_username}{random.randint(1000, 9999)}"
                break
        
        return username

    def validate_unique_email(self, email):
        """
        Ensure email uniqueness
        """
        if User.objects.filter(email=email).exists():
            # Email exists, we'll handle this in pre_social_login
            return False
        return True