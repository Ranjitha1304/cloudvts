# storage_app/utils.py
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_welcome_email(user):
    """Send welcome email to new user"""
    try:
        print(f"📧 Sending welcome email to: {user.email}")
        
        subject = 'Welcome to CloudVTS!'
        
        context = {
            'user': user,
            'dashboard_url': settings.SITE_URL + '/dashboard/' if hasattr(settings, 'SITE_URL') else 'http://localhost:8000/dashboard/',
            'site_url': settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        }
        
        html_message = render_to_string('emails/welcome_email.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        result = email.send()
        
        print(f"✅ Welcome email sent to {user.email}")
        return True
    except Exception as e:
        print(f"❌ Welcome email failed for {user.email}: {e}")
        return False

def send_subscription_email(user, old_plan, new_plan, change_type):
    """Send subscription change email"""
    try:
        print(f"📧 Sending subscription email to: {user.email}")
        print(f"   Change: {change_type}, From: {old_plan.name}, To: {new_plan.name}")
        
        subject = f'Subscription {change_type.title()} - CloudVTS'
        
        context = {
            'user': user,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'change_type': change_type,
            'site_url': settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        }
        
        html_message = render_to_string('emails/subscription_change.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        result = email.send()
        
        print(f"✅ Subscription email sent to {user.email}")
        return True
    except Exception as e:
        print(f"❌ Subscription email failed for {user.email}: {e}")
        return False

def send_payment_success_email(user, plan, amount):
    """Send payment success email"""
    try:
        print(f"📧 Sending payment success email to: {user.email}")
        print(f"   Plan: {plan.name}, Amount: ₹{amount}")
        
        subject = 'Payment Successful - CloudVTS'
        
        context = {
            'user': user,
            'plan': plan,
            'amount': amount,
            'site_url': settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        }
        
        html_message = render_to_string('emails/payment_success.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        result = email.send()
        
        print(f"✅ Payment success email sent to {user.email}")
        return True
    except Exception as e:
        print(f"❌ Payment success email failed for {user.email}: {e}")
        return False

def send_storage_alert_email(user, usage_percent):
    """Send storage alert email"""
    try:
        print(f"📧 Sending storage alert to: {user.email}")
        
        subject = f'Storage Alert - {usage_percent}% Used'
        
        context = {
            'user': user,
            'usage_percent': usage_percent,
            'site_url': settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'http://localhost:8000'
        }
        
        html_message = render_to_string('emails/storage_alert.html', context)
        plain_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_message, "text/html")
        result = email.send()
        
        print(f"✅ Storage alert sent to {user.email}")
        return True
    except Exception as e:
        print(f"❌ Storage alert failed for {user.email}: {e}")
        return False
    

def get_max_file_size_for_plan(plan):
    """Get maximum file size allowed for a storage plan"""
    plan_limits = {
        'free': 100 * 1024 * 1024,  # 100MB for free plan
        'basic': 2 * 1024 * 1024 * 1024,  # 2GB for basic plan
        'pro': 5 * 1024 * 1024 * 1024,  # 5GB for pro plan
        'enterprise': 10 * 1024 * 1024 * 1024,  # 10GB for enterprise plan
    }
    return plan_limits.get(plan.plan_type, 100 * 1024 * 1024)  # Default to 100MB