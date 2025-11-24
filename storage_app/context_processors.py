from django.conf import settings

def stripe_keys(request):
    return {
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY,
    }

def user_plan(request):
    if request.user.is_authenticated:
        try:
            from .models import UserProfile
            user_profile = UserProfile.objects.get(user=request.user)
            return {
                'user_plan': user_profile.storage_plan,
                'user_profile': user_profile,
            }
        except:
            return {}
    return {}