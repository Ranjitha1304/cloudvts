from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Sum, Q 
from django.utils import timezone
import os
import json
import stripe
from datetime import datetime
from django.conf import settings

from .models import File, UserProfile, ShareLink, StoragePlan, Folder, Subscription, Trash
from .forms import CustomUserCreationForm, FileUploadForm, FileShareForm, FolderCreateForm, MoveFileForm, StoragePlanForm
from .utils import send_welcome_email, send_subscription_email, send_payment_success_email

from django.contrib.auth.models import User
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage

from django.contrib.auth import views as auth_views
from django.contrib.auth import update_session_auth_hash

from django.contrib import messages

from django.template.defaultfilters import filesizeformat


# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Landing Page
def landing_page(request):
    """Landing page with plan selection"""
    plans = StoragePlan.objects.filter(is_active=True).order_by('price')
    return render(request, 'landing.html', {'plans': plans})

# Authentication Views
def register_view(request):
    """Enhanced registration with plan selection"""
    initial_plan_id = request.GET.get('plan')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            plan_id = request.POST.get('plan_id')
            print(f"📝 Registration form valid, plan_id: {plan_id}")
            
            try:
                if plan_id:
                    selected_plan = StoragePlan.objects.get(id=plan_id)
                else:
                    selected_plan = StoragePlan.objects.get(plan_type='free')
            except StoragePlan.DoesNotExist:
                selected_plan = StoragePlan.objects.create(
                    name='Free Plan',
                    plan_type='free',
                    max_storage_size=5 * 1024 * 1024 * 1024,
                    price=0,
                    billing_period='yearly',
                    is_active=True,
                    features=['5GB Storage', 'Basic Support', 'File Sharing']
                )
            
            print(f"💰 Selected plan: {selected_plan.name}, Price: ₹{selected_plan.price}")
            
            # For free plans: create user and login immediately
            if selected_plan.price == 0:
                print("🆓 Free plan selected - creating user immediately")
                user = form.save()
                
                user_profile, created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'storage_plan': selected_plan}
                )
                
                if not created:
                    user_profile.storage_plan = selected_plan
                    user_profile.save()
                
                try:
                    send_welcome_email(user)
                except Exception as e:
                    print(f"Failed to send welcome email: {e}")
                
                # Authenticate and login user
                user = authenticate(
                    request, 
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password1']
                )
                if user is not None:
                    login(request, user)
                    return redirect('dashboard')
                else:
                    return redirect('login')
            
            # For paid plans: store registration data in session and redirect to payment
            else:
                print("💳 Paid plan selected - storing registration data and redirecting to payment")
                # Store form data and plan in session
                request.session['pending_registration'] = {
                    'username': form.cleaned_data['username'],
                    'email': form.cleaned_data['email'],
                    'password': form.cleaned_data['password1'],
                    'plan_id': str(selected_plan.id)
                }
                request.session['selected_plan_id'] = selected_plan.id
                
                print(f"📦 Stored pending registration for: {form.cleaned_data['username']}")
                print(f"📦 Session data: {request.session.get('pending_registration')}")
                
                # Redirect to payment page
                return redirect('create_checkout_session', plan_id=selected_plan.id)
        
        else:
            print(f"❌ Form errors: {form.errors}")
            plans = StoragePlan.objects.filter(is_active=True).order_by('price')
            return render(request, 'register.html', {
                'form': form, 
                'plans': plans,
                'error': 'Please correct the errors below.'
            })
    
    else:
        form = CustomUserCreationForm()
        if initial_plan_id:
            try:
                initial_plan = StoragePlan.objects.get(id=initial_plan_id)
            except StoragePlan.DoesNotExist:
                initial_plan = StoragePlan.objects.get(plan_type='free')
        else:
            initial_plan = StoragePlan.objects.get(plan_type='free')
    
    plans = StoragePlan.objects.filter(is_active=True).order_by('price')
    return render(request, 'register.html', {
        'form': form, 
        'plans': plans,
        'initial_plan_id': initial_plan_id
    })

def login_view(request):
    """Login view with case-insensitive authentication"""
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        
        print(f"🔐 LOGIN ATTEMPT - Username: {username}, Password: {password[:2]}...")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            print(f"✅ LOGIN SUCCESS - User: {user.username} (ID: {user.id})")
            
            # Clear any existing session completely
            request.session.flush()
            
            login(request, user)
            
            # Handle "Remember Me" functionality
            remember_me = request.POST.get('remember_me')
            
            if remember_me:
                # "Remember Me" CHECKED - persist for 2 weeks
                request.session.set_expiry(1209600)  # 14 days
                print("🔐 Session: Remember Me ENABLED (2 weeks)")
            else:
                # "Remember Me" UNCHECKED - Use sessionStorage for tab-specific sessions
                request.session.set_expiry(86400)  # 24 hours as fallback
                print("🔐 Session: Remember Me DISABLED (tab-based session)")
            
            # Force session save
            request.session.save()
            
            return redirect('dashboard')
        else:
            print(f"❌ LOGIN FAILED - Username: {username}")
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    
    return render(request, 'login.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('landing')

# Dashboard Views
@login_required
def dashboard(request):
    """Main dashboard view - EXCLUDE DELETED FILES"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        free_plan, created = StoragePlan.objects.get_or_create(
            plan_type='free',
            defaults={
                'name': 'Free Plan',
                'max_storage_size': 5 * 1024 * 1024 * 1024,
                'price': 0,
                'billing_period': 'yearly',
                'is_active': True,
                'features': ['5GB Storage', 'Basic Support', 'File Sharing']
            }
        )
        user_profile = UserProfile.objects.create(user=request.user, storage_plan=free_plan)
    
    # EXCLUDE DELETED FILES
    files = File.objects.filter(owner=request.user, is_deleted=False).order_by('-uploaded_at')
    total_files = files.count()
    
    total_size = files.aggregate(Sum('size'))['size__sum'] or 0
    user_profile.used_storage = total_size
    user_profile.save()
    
    view_mode = request.session.get('dashboard_view_mode', 'grid')
    
    context = {
        'user_profile': user_profile,
        'files': files[:8],
        'total_files': total_files,
        'total_size': total_size,
        'storage_usage_percent': user_profile.get_storage_usage_percent(),
        'view_mode': view_mode,
    }
    return render(request, 'dashboard.html', context)

@login_required
def toggle_dashboard_view(request):
    """Toggle between grid and list view"""
    if request.method == 'POST':
        current_view = request.session.get('dashboard_view_mode', 'grid')
        new_view = 'list' if current_view == 'grid' else 'grid'
        request.session['dashboard_view_mode'] = new_view
        return JsonResponse({'success': True, 'view_mode': new_view})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# File Management Views
@login_required
def file_list(request, folder_id=None):
    """File list with folder support - EXCLUDE DELETED ITEMS"""
    current_folder = None
    if folder_id:
        current_folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_deleted=False)
    
    # EXCLUDE DELETED FILES AND FOLDERS
    files = File.objects.filter(owner=request.user, folder=current_folder, is_deleted=False)
    folders = Folder.objects.filter(owner=request.user, parent_folder=current_folder, is_deleted=False).order_by('name')
    
    file_type_filter = request.GET.get('file_type', '')
    date_filter = request.GET.get('date_filter', '')
    starred_filter = request.GET.get('starred', '')
    
    if file_type_filter:
        files = filter_files_by_type(files, file_type_filter)
    if date_filter:
        files = filter_files_by_date(files, date_filter)
    if starred_filter == 'true':
        files = files.filter(is_starred=True)
        folders = folders.filter(is_starred=True)
    
    files = files.order_by('-uploaded_at')
    
    # PAGINATION - Enhanced with items per page
    items_per_page = int(request.GET.get('per_page', 10))  # Default to 10 items per page
    page_number = request.GET.get('page', 1)
    paginator = Paginator(files, items_per_page)
    
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    all_folders = Folder.objects.filter(owner=request.user, is_deleted=False)
    if current_folder:
        all_folders = all_folders.exclude(id=current_folder.id)
    
    context = {
        'files': page_obj,
        'page_obj': page_obj,
        'folders': folders,
        'current_folder': current_folder,
        'all_folders': all_folders,
        'folder_form': FolderCreateForm(),
        'file_type_filter': file_type_filter,
        'date_filter': date_filter,
        'starred_filter': starred_filter == 'true',
        'items_per_page': items_per_page,
    }
    return render(request, 'file_list.html', context)

@login_required
def starred_files(request):
    """Combined view for starred files and folders - EXCLUDE DELETED"""
    starred_files = File.objects.filter(owner=request.user, is_starred=True, is_deleted=False)
    starred_folders = Folder.objects.filter(owner=request.user, is_starred=True, is_deleted=False)
    
    context = {
        'starred_files': starred_files,
        'starred_folders': starred_folders,
        'is_starred_view': True,
    }
    return render(request, 'starred.html', context)

@login_required
def upload_file(request):
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file_obj = form.save(commit=False)
            file_obj.owner = request.user
            file_obj.size = file_obj.file.size
            file_obj.name = file_obj.file.name
            file_obj.file_type = os.path.splitext(file_obj.file.name)[1].lower()
            
            user_profile = UserProfile.objects.get(user=request.user)
            
            # CHECK 1: File size limit
            if file_obj.size > user_profile.storage_plan.max_file_size:
                return JsonResponse({
                    'success': False,
                    'error': f'File size exceeds limit. Maximum allowed: {filesizeformat(user_profile.storage_plan.max_file_size)}'
                })
            
            # CHECK 2: Storage limit
            if user_profile.used_storage + file_obj.size > user_profile.storage_plan.max_storage_size:
                return JsonResponse({
                    'success': False,
                    'error': 'Storage limit exceeded'
                })
            
            file_obj.save()

            # ✅ FIX: Update used storage
            user_profile.used_storage += file_obj.size
            user_profile.save()

            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Invalid file'})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def download_file(request, file_id):
    """Generate signed URL for file download"""
    try:
        file_obj = get_object_or_404(File, id=file_id, owner=request.user)
        
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
        
        file_key = file_obj.file.name
        possible_keys = [
            file_key,
            f"media/{file_key}",
        ]
        
        actual_key = file_key
        for test_key in possible_keys:
            try:
                s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_key)
                actual_key = test_key
                break
            except:
                continue
        
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': actual_key,
                'ResponseContentDisposition': f'attachment; filename="{file_obj.name}"'
            },
            ExpiresIn=3600
        )
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'download_url': presigned_url,
                'filename': file_obj.name
            })
        else:
            return redirect(presigned_url)
        
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        else:
            return JsonResponse({'success': False, 'error': str(e)})

@login_required
def preview_file(request, file_id):
    """Preview file in full page"""
    try:
        file_obj = get_object_or_404(File, id=file_id, owner=request.user)
        
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
        
        file_key = file_obj.file.name
        possible_keys = [
            file_key,
            f"media/{file_key}",
        ]
        
        actual_key = file_key
        for test_key in possible_keys:
            try:
                s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_key)
                actual_key = test_key
                break
            except:
                continue
        
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': actual_key,
                'ResponseContentDisposition': 'inline'
            },
            ExpiresIn=3600
        )
        
        file_type = file_obj.file_type.lower()
        previewable_types = {
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
            'pdf': ['.pdf'],
            'text': ['.txt', '.csv', '.log', '.md'],
            'code': ['.js', '.py', '.java', '.cpp', '.c', '.php', '.xml', '.json'],
            'video': ['.mp4', '.avi', '.mov', '.webm'],
            'audio': ['.mp3', '.wav', '.ogg', '.m4a'],
            'office': ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'],
            'html': ['.html', '.htm'],
        }
        
        file_category = 'other'
        for category, extensions in previewable_types.items():
            if file_type in extensions:
                file_category = category
                break
        
        text_content = None
        if file_category in ['text', 'code']:
            try:
                response = s3_client.get_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=actual_key
                )
                content = response['Body'].read()
                
                try:
                    text_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        text_content = content.decode('latin-1')
                    except UnicodeDecodeError:
                        text_content = "⚠️ Unable to decode file content (binary file)"
                
                if len(text_content) > 1024 * 1024:
                    text_content = text_content[:1024 * 1024] + "\n\n... (content truncated - file too large)"
                    
            except Exception as e:
                print(f"Error loading text content: {e}")
                text_content = f"⚠️ Error loading file content: {str(e)}"
        
        context = {
            'file': file_obj,
            'preview_url': presigned_url,
            'file_category': file_category,
            'text_content': text_content,
        }
        
        return render(request, 'file_preview.html', context)
        
    except Exception as e:
        print(f"Preview error: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

# Starring functionality
@login_required
def toggle_star_file(request, file_id):
    """Toggle star status for file"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user)
            file_obj.is_starred = not file_obj.is_starred
            file_obj.save()
            
            return JsonResponse({
                'success': True, 
                'is_starred': file_obj.is_starred,
                'message': f'File {"starred" if file_obj.is_starred else "unstarred"} successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def toggle_star_folder(request, folder_id):
    """Toggle star status for folder"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            folder.is_starred = not folder.is_starred
            folder.save()
            
            return JsonResponse({
                'success': True, 
                'is_starred': folder.is_starred,
                'message': f'Folder {"starred" if folder.is_starred else "unstarred"} successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Folder Management
@login_required
def create_folder(request):
    """Create new folder"""
    if request.method == 'POST':
        form = FolderCreateForm(request.POST)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.owner = request.user
            folder.save()
            return JsonResponse({'success': True, 'folder_id': folder.id, 'folder_name': folder.name})
        else:
            return JsonResponse({'success': False, 'error': form.errors})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def move_file(request, file_id):
    """Move file to folder"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user)
            
            data = json.loads(request.body)
            folder_id = data.get('folder')
            
            print(f"📁 Moving file {file_obj.name} (ID: {file_obj.id}) to folder ID: {folder_id}")
            
            if folder_id:
                folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
                old_folder = file_obj.folder
                file_obj.folder = folder
                file_obj.save()
                
                print(f"✅ File {file_obj.name} moved from {old_folder.name if old_folder else 'root'} to {folder.name}")
                return JsonResponse({
                    'success': True, 
                    'message': f'File moved successfully to "{folder.name}"'
                })
            else:
                old_folder = file_obj.folder
                file_obj.folder = None
                file_obj.save()
                
                print(f"✅ File {file_obj.name} moved from {old_folder.name if old_folder else 'root'} to root folder")
                return JsonResponse({
                    'success': True, 
                    'message': 'File moved successfully to root folder'
                })
            
        except Folder.DoesNotExist:
            print(f"❌ Folder not found: {folder_id}")
            return JsonResponse({
                'success': False, 
                'error': 'Folder not found'
            })
        except json.JSONDecodeError:
            print("❌ Invalid JSON in request body")
            return JsonResponse({
                'success': False, 
                'error': 'Invalid request data'
            })
        except Exception as e:
            print(f"❌ Error moving file: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': str(e)
            })
    
    return JsonResponse({
        'success': False, 
        'error': 'Invalid request method'
    })

@login_required
def delete_folder(request, folder_id):
    """Delete folder (must be empty)"""
    if request.method == 'POST':
        folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
        
        if folder.files.exists() or folder.subfolders.exists():
            return JsonResponse({
                'success': False, 
                'error': 'Folder is not empty. Please delete all files and subfolders first.'
            })
        
        folder.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Sharing functionality - FIXED VERSION
@login_required
def toggle_file_visibility(request, file_id):
    """Toggle file between public and private"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user)
            file_obj.is_public = not file_obj.is_public
            file_obj.save()
            
            return JsonResponse({
                'success': True, 
                'is_public': file_obj.is_public,
                'message': f'File is now {"public" if file_obj.is_public else "private"}'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def create_share_link(request, file_id):
    """Create shareable link for file - FIXED PASSWORD LOGIC"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user)
            
            # Create new share link
            share_link = ShareLink.objects.create(file=file_obj)
            
            expires_in = request.POST.get('expires_in')
            if expires_in and expires_in.isdigit():
                share_link.expires_at = timezone.now() + timezone.timedelta(days=int(expires_in))
            
            # FIXED: Simplified password logic
            enable_password = request.POST.get('enable_password') == 'on'
            password = request.POST.get('password', '').strip()
            
            print(f"🔐 Password protection - enabled: {enable_password}, password provided: {bool(password)}")
            
            # Only set password if both conditions are met
            if enable_password and password:
                share_link.set_password(password)
                print(f"✅ Password protection enabled for share {share_link.token}")
            else:
                # Ensure password protection is disabled
                share_link.require_password = False
                share_link.password_hash = None
                share_link.save()
                print(f"❌ Password protection disabled for share {share_link.token}")
            
            share_url = request.build_absolute_uri(f'/share/{share_link.token}/')
            
            return JsonResponse({
                'success': True, 
                'share_url': share_url,
                'expires_at': share_link.expires_at.isoformat() if share_link.expires_at else None,
                'has_password': share_link.has_password()
            })
                
        except Exception as e:
            print(f"❌ Error creating share link: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def share_file(request, token):
    """Handle shared file access - FIXED PASSWORD FLOW"""
    try:
        share_link = get_object_or_404(ShareLink, token=token, is_active=True)
        
        if share_link.expires_at and share_link.expires_at < timezone.now():
            return render(request, 'share_expired.html', {
                'error': 'This share link has expired'
            })
        
        # Check if password protection is enabled
        if share_link.has_password():
            # Check if user has verified access
            if not request.session.get(f'share_verified_{token}'):
                return render(request, 'share_password.html', {
                    'share_link': share_link,
                    'file': share_link.file,
                    'token': token,
                    'type': 'file'
                })
        
        file_obj = share_link.file
        
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
        
        file_key = file_obj.file.name
        possible_keys = [
            file_key,
            f"media/{file_key}",
        ]
        
        actual_key = file_key
        for test_key in possible_keys:
            try:
                s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_key)
                actual_key = test_key
                break
            except:
                continue
        
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': actual_key,
                'ResponseContentDisposition': f'attachment; filename="{file_obj.name}"'
            },
            ExpiresIn=3600
        )
        
        return render(request, 'share_file.html', {
            'file': file_obj,
            'share_link': share_link,
            'download_url': presigned_url
        })
        
    except Http404:
        return render(request, 'share_error.html', {
            'error': 'Share link not found or inactive'
        })
    except Exception as e:
        return render(request, 'share_error.html', {
            'error': f'Error accessing file: {str(e)}'
        })

def public_file_access(request, file_id):
    """Direct access to public files"""
    try:
        file_obj = get_object_or_404(File, id=file_id, is_public=True)
        
        import boto3
        from botocore.client import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4')
        )
        
        file_key = file_obj.file.name
        possible_keys = [
            file_key,
            f"media/{file_key}",
        ]
        
        actual_key = file_key
        for test_key in possible_keys:
            try:
                s3_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_key)
                actual_key = test_key
                break
            except:
                continue
        
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': actual_key,
                'ResponseContentDisposition': f'attachment; filename="{file_obj.name}"'
            },
            ExpiresIn=3600
        )
        
        public_url = request.build_absolute_uri(f'/public/file/{file_obj.id}/')
        
        return render(request, 'public_file.html', {
            'file': file_obj,
            'download_url': presigned_url,
            'public_url': public_url
        })
        
    except Http404:
        return render(request, 'public_file_error.html', {
            'error': 'File not found or not publicly accessible'
        })
    except Exception as e:
        return render(request, 'public_file_error.html', {
            'error': f'Error accessing file: {str(e)}'
        })

# Trash Management
@login_required
def trash_view(request):
    """View files and folders in trash with auto-delete calculations"""
    trash_items = Trash.objects.filter(user=request.user).select_related('file', 'folder')
    
    # Separate files and folders
    files_in_trash = [item.file for item in trash_items if item.file and item.file.is_deleted]
    folders_in_trash = [item.folder for item in trash_items if item.folder and item.folder.is_deleted]
    
    # Calculate total size (only files)
    total_size = sum(file.size for file in files_in_trash if file)
    
    # Add auto-delete calculations to each file and folder
    for item in trash_items:
        if item.file and item.file.is_deleted:
            item.file.auto_delete_date = item.scheduled_permanent_deletion
            item.file.deleted_at = item.deleted_at
            # Calculate days until auto-delete
            days_until = (item.scheduled_permanent_deletion - timezone.now()).days
            item.file.days_until_auto_delete = max(0, days_until)
            item.file.will_be_deleted_soon = days_until <= 7
        
        if item.folder and item.folder.is_deleted:
            item.folder.auto_delete_date = item.scheduled_permanent_deletion
            item.folder.deleted_at = item.deleted_at
            days_until = (item.scheduled_permanent_deletion - timezone.now()).days
            item.folder.days_until_auto_delete = max(0, days_until)
            item.folder.will_be_deleted_soon = days_until <= 7
    
    context = {
        'files': files_in_trash,
        'folders': folders_in_trash,
        'trash_count': len(files_in_trash) + len(folders_in_trash),
        'total_size': total_size,
        'is_trash_view': True,
    }
    return render(request, 'trash.html', context)


@login_required
def move_to_trash(request, file_id):
    """Move file to trash"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user)
            
            Trash.objects.create(
                user=request.user,
                file=file_obj,
                original_folder=file_obj.folder,
                scheduled_permanent_deletion=timezone.now() + timezone.timedelta(days=30)
            )
            
            file_obj.is_deleted = True
            file_obj.save()
            
            return JsonResponse({
                'success': True,
                'message': 'File moved to trash'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def restore_file(request, file_id):
    """Restore file from trash"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user, is_deleted=True)
            trash_item = get_object_or_404(Trash, file=file_obj, user=request.user)
            
            file_obj.is_deleted = False
            file_obj.save()
            trash_item.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'File restored successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def permanent_delete_file(request, file_id):
    """Permanently delete file from trash"""
    if request.method == 'POST':
        try:
            file_obj = get_object_or_404(File, id=file_id, owner=request.user, is_deleted=True)
            trash_item = get_object_or_404(Trash, file=file_obj, user=request.user)
            
            # ✅ Update user storage before deletion
            user_profile = UserProfile.objects.get(user=request.user)
            user_profile.used_storage -= file_obj.size
            user_profile.save()
            
            file_obj.file.delete(save=False)
            trash_item.delete()
            file_obj.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'File permanently deleted'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def empty_trash(request):
    """Permanently delete all files in trash"""
    if request.method == 'POST':
        try:
            trash_items = Trash.objects.filter(user=request.user)
            deleted_count = 0
            
            for trash_item in trash_items:
                file_obj = trash_item.file
                file_obj.file.delete(save=False)
                trash_item.delete()
                file_obj.delete()
                deleted_count += 1
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully deleted {deleted_count} files',
                'deleted_count': deleted_count
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Payment & Subscription Views

def pricing_plans(request):
    """Display pricing plans - PUBLIC ACCESS"""
    plans = StoragePlan.objects.filter(is_active=True).order_by('price')
    
    # Only get user-specific data if user is authenticated
    current_plan = None
    if request.user.is_authenticated:
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            current_plan = user_profile.storage_plan
        except UserProfile.DoesNotExist:
            pass
    
    context = {
        'plans': plans,
        'current_plan': current_plan,
    }
    return render(request, 'pricing.html', context)


# Remove @login_required decorator from this function
def create_checkout_session(request, plan_id):
    """Create Stripe checkout session - handles both existing users and new registrations"""
    try:
        print(f"🔧 Creating checkout session for plan_id: {plan_id}")
        
        plan = get_object_or_404(StoragePlan, id=plan_id, is_active=True)
        print(f"📋 Plan found: {plan.name}, Price: ₹{plan.price}")
        
        # Check if this is a new registration (user not logged in yet)
        pending_registration = request.session.get('pending_registration')
        
        if plan.price == 0:
            print("🆓 Handling free plan...")
            
            # If it's a new registration for free plan, create user and login
            if pending_registration:
                # Create the user
                user = User.objects.create_user(
                    username=pending_registration['username'],
                    email=pending_registration['email'],
                    password=pending_registration['password']
                )
                
                # Create user profile
                user_profile = UserProfile.objects.create(user=user, storage_plan=plan)
                
                # Clear pending registration
                del request.session['pending_registration']
                del request.session['selected_plan_id']
                
                # Login user
                login(request, user)
                
                try:
                    send_welcome_email(user)
                except Exception as e:
                    print(f"Failed to send welcome email: {e}")
                
                return redirect('dashboard')
            else:
                # Existing user switching to free plan
                user_profile = UserProfile.objects.get(user=request.user)
                old_plan = user_profile.storage_plan
                user_profile.storage_plan = plan
                user_profile.save()
                
                if old_plan and old_plan.price > plan.price:
                    send_subscription_email(request.user, old_plan, plan, 'downgrade')
                
                return redirect('dashboard')
        
        # For paid plans
        if not plan.stripe_price_id:
            print(f"❌ Missing Stripe price ID for plan: {plan.name}")
            messages.error(request, 'This plan is not configured for payments. Please contact support.')
            return redirect('pricing_plans')
        
        print(f"💰 Stripe price ID: {plan.stripe_price_id}")
        
        # Handle customer creation based on whether user is logged in or new registration
        stripe_customer_id = None
        
        if request.user.is_authenticated:
            # Existing user
            user_profile = UserProfile.objects.get(user=request.user)
            
            if not user_profile.stripe_customer_id:
                print("👤 Creating new Stripe customer for existing user...")
                customer = stripe.Customer.create(
                    email=request.user.email,
                    name=request.user.get_full_name() or request.user.username,
                    metadata={'user_id': request.user.id}
                )
                user_profile.stripe_customer_id = customer.id
                user_profile.save()
                stripe_customer_id = customer.id
                print(f"✅ Created customer: {customer.id}")
            else:
                stripe_customer_id = user_profile.stripe_customer_id
                print(f"👤 Using existing customer: {stripe_customer_id}")
        else:
            # New registration - create customer with pending registration data
            if pending_registration:
                print("👤 Creating new Stripe customer for pending registration...")
                customer = stripe.Customer.create(
                    email=pending_registration['email'],
                    name=pending_registration['username'],
                    metadata={'pending_user': True}
                )
                stripe_customer_id = customer.id
                print(f"✅ Created customer for pending registration: {customer.id}")
            else:
                print("❌ No pending registration found for unauthenticated user")
                messages.error(request, 'Registration data not found. Please try registering again.')
                return redirect('register')
        
        if not stripe_customer_id:
            print("❌ No customer ID available")
            messages.error(request, 'Payment configuration error.')
            return redirect('pricing_plans')
        
        success_url = request.build_absolute_uri('/payment/success/') + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = request.build_absolute_uri('/pricing/')
        
        print(f"🔗 Success URL: {success_url}")
        print(f"🔗 Cancel URL: {cancel_url}")
        
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': plan.stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'plan_id': str(plan.id),
                'user_id': str(request.user.id) if request.user.is_authenticated else 'pending',
                'pending_registration': 'true' if pending_registration else 'false'
            }
        )
        
        print(f"✅ Checkout session created: {checkout_session.id}")
        print(f"🔗 Checkout URL: {checkout_session.url}")
        
        return redirect(checkout_session.url)
        
    except StoragePlan.DoesNotExist:
        print(f"❌ Plan not found: {plan_id}")
        messages.error(request, 'Plan not found or inactive.')
        return redirect('pricing_plans')
    except Exception as e:
        print(f"❌ Stripe error: {str(e)}")
        messages.error(request, f'Payment configuration error: {str(e)}')
        return redirect('pricing_plans')
    


def payment_success(request):
    """Handle successful payment - creates user account for new registrations"""
    session_id = request.GET.get('session_id')
    print(f"🎯 Payment success called")
    print(f"📦 Session ID: {session_id}")
    
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            print(f"💰 Payment status: {session.payment_status}")
            print(f"📋 Session metadata: {session.metadata}")
            
            if session.payment_status == 'paid':
                plan_id = session.metadata.get('plan_id')
                user_id = session.metadata.get('user_id')
                is_pending_registration = session.metadata.get('pending_registration') == 'true'
                
                print(f"📝 Plan ID: {plan_id}, User ID: {user_id}, Pending Registration: {is_pending_registration}")
                
                # Handle new registration
                if is_pending_registration and user_id == 'pending':
                    pending_registration = request.session.get('pending_registration')
                    print(f"📦 Pending registration data: {pending_registration}")
                    
                    if pending_registration:
                        # Check if user already exists (case-insensitive)
                        existing_user = User.objects.filter(username__iexact=pending_registration['username']).first()
                        if existing_user:
                            print(f"❌ User {pending_registration['username']} already exists")
                            messages.error(request, 'User already exists. Please try a different username.')
                            return redirect('register')
                        
                        # Create the user account
                        user = User.objects.create_user(
                            username=pending_registration['username'],
                            email=pending_registration['email'],
                            password=pending_registration['password']
                        )
                        
                        plan = StoragePlan.objects.get(id=plan_id)
                        
                        # Create user profile with the paid plan
                        try:
                            # Get existing user profile (created by signal)
                            user_profile = UserProfile.objects.get(user=user)
                            # Update with paid plan details
                            user_profile.storage_plan = plan
                            user_profile.stripe_customer_id = session.customer
                            user_profile.save()
                            print(f"✅ Updated existing user profile for {user.username}")
                        except UserProfile.DoesNotExist:
                            # Fallback: create if doesn't exist (shouldn't happen with signal)
                            user_profile = UserProfile.objects.create(
                                user=user,
                                storage_plan=plan,
                                stripe_customer_id=session.customer
                            )
                            print(f"✅ Created new user profile for {user.username}")
                        
                        # Clear pending registration data
                        if 'pending_registration' in request.session:
                            del request.session['pending_registration']
                        if 'selected_plan_id' in request.session:
                            del request.session['selected_plan_id']
                        

                        from django.contrib.auth import authenticate
                        user = authenticate(
                            request, 
                            username=pending_registration['username'],
                            password=pending_registration['password']
                        )
                        if user is not None:
                            login(request, user)
                            print(f"✅ User {user.username} created and logged in successfully")
                        else:
                            print(f"❌ Failed to authenticate user {pending_registration['username']}")
                            # You might want to handle this case appropriately

                        
                        print(f"🔍 DEBUG: User ID: {user.id}, Username: {user.username}, Email: {user.email}")
                        print(f"🔍 DEBUG: User exists in DB: {User.objects.filter(id=user.id).exists()}")
                        
                        # Send emails with individual error handling
                        import time
                        time.sleep(1)  # Small delay to ensure user is fully saved
                        
                        # Send welcome email with detailed logging
                        try:
                            print(f"🎯 Attempting to send welcome email to {user.email}")
                            welcome_sent = send_welcome_email(user)
                            if welcome_sent:
                                print(f"✅ Welcome email sent successfully to {user.email}")
                            else:
                                print(f"❌ Welcome email failed to send to {user.email}")
                        except Exception as e:
                            print(f"❌ Welcome email exception: {str(e)}")
                            import traceback
                            traceback.print_exc()

                        # Send payment success email
                        try:
                            print(f"🎯 Attempting to send payment success email to {user.email}")
                            payment_sent = send_payment_success_email(user, plan, plan.price)
                            if payment_sent:
                                print(f"✅ Payment success email sent successfully to {user.email}")
                            else:
                                print(f"❌ Payment success email failed to send to {user.email}")
                        except Exception as e:
                            print(f"❌ Payment success email exception: {str(e)}")
                            import traceback
                            traceback.print_exc()
                        
                        # Create subscription record
                        try:
                            if hasattr(session, 'subscription') and session.subscription:
                                subscription = stripe.Subscription.retrieve(session.subscription)
                                
                                Subscription.objects.update_or_create(
                                    stripe_subscription_id=subscription.id,
                                    defaults={
                                        'user': user,
                                        'plan': plan,
                                        'status': subscription.status,
                                        'current_period_start': datetime.fromtimestamp(subscription.current_period_start) if subscription.current_period_start else None,
                                        'current_period_end': datetime.fromtimestamp(subscription.current_period_end) if subscription.current_period_end else None,
                                        'cancel_at_period_end': subscription.cancel_at_period_end,
                                    }
                                )
                                print(f"📋 Subscription record created")
                        except Exception as sub_error:
                            print(f"❌ Subscription retrieval error: {sub_error}")
                        
                        return render(request, 'payment_success.html', {
                            'plan': plan,
                            'is_new_registration': True
                        })
                    else:
                        print("❌ No pending registration data found in session")
                        messages.error(request, 'Registration data not found. Please contact support.')
                        return redirect('register')
                
                # Handle existing user plan upgrade
                elif request.user.is_authenticated and str(request.user.id) == user_id:
                    plan = StoragePlan.objects.get(id=plan_id)
                    user_profile = UserProfile.objects.get(user=request.user)
                    old_plan = user_profile.storage_plan
                    
                    user_profile.storage_plan = plan
                    user_profile.save()
                    
                    subscription_info = None
                    try:
                        if hasattr(session, 'subscription') and session.subscription:
                            subscription = stripe.Subscription.retrieve(session.subscription)
                            subscription_info = subscription
                            
                            Subscription.objects.update_or_create(
                                stripe_subscription_id=subscription.id,
                                defaults={
                                    'user': request.user,
                                    'plan': plan,
                                    'status': subscription.status,
                                    'current_period_start': datetime.fromtimestamp(subscription.current_period_start) if subscription.current_period_start else None,
                                    'current_period_end': datetime.fromtimestamp(subscription.current_period_end) if subscription.current_period_end else None,
                                    'cancel_at_period_end': subscription.cancel_at_period_end,
                                }
                            )
                    except Exception as sub_error:
                        print(f"Subscription retrieval error (non-critical): {sub_error}")
                    
                    try:
                        if old_plan.id != plan.id:
                            if float(old_plan.price) < float(plan.price):
                                send_subscription_email(request.user, old_plan, plan, 'upgrade')
                            elif float(old_plan.price) > float(plan.price):
                                send_subscription_email(request.user, old_plan, plan, 'downgrade')
                            else:
                                send_subscription_email(request.user, old_plan, plan, 'change')
                            
                            send_payment_success_email(request.user, plan, plan.price)
                            print(f"✅ Emails sent for plan change: {old_plan.name} -> {plan.name}")
                    except Exception as email_error:
                        print(f"❌ Email sending failed: {email_error}")
                    
                    return render(request, 'payment_success.html', {
                        'plan': plan,
                        'subscription_id': subscription_info.id if subscription_info else None,
                        'is_new_registration': False
                    })
                else:
                    print("❌ User ID mismatch or user not authenticated")
                    print(f"Authenticated: {request.user.is_authenticated}, Request User ID: {request.user.id if request.user.is_authenticated else 'None'}, Session User ID: {user_id}")
                
        except Exception as e:
            print(f"❌ Payment success error: {e}")
            import traceback
            traceback.print_exc()
    
    print("❌ No session ID or payment not successful")
    return render(request, 'payment_success.html')


@login_required
def payment_cancel(request):
    """Handle canceled payment"""
    return render(request, 'payment_cancel.html')

@login_required
def subscription_management(request):
    """Manage user subscription"""
    try:
        user_profile = UserProfile.objects.get(user=request.user)
        subscription = Subscription.objects.filter(user=request.user, status='active').first()
        
        if subscription and user_profile.stripe_customer_id:
            stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            upcoming_invoice = stripe.Invoice.upcoming(customer=user_profile.stripe_customer_id)
            
            context = {
                'subscription': subscription,
                'stripe_subscription': stripe_subscription,
                'upcoming_invoice': upcoming_invoice,
                'user_profile': user_profile,
            }
            return render(request, 'subscription_management.html', context)
    
    except Exception as e:
        print(f"Subscription management error: {e}")
    
    return redirect('pricing_plans')

@login_required
def cancel_subscription(request):
    """Cancel user subscription"""
    if request.method == 'POST':
        try:
            subscription = Subscription.objects.get(user=request.user, status='active')
            
            canceled_subscription = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            
            subscription.cancel_at_period_end = True
            subscription.save()
            
            return JsonResponse({'success': True, 'message': 'Subscription will cancel at period end'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Utility functions
def filter_files_by_type(files_queryset, file_type):
    """Filter files by file type"""
    file_type_groups = {
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
        'document': ['.doc', '.docx', '.txt', '.rtf', '.odt'],
        'pdf': ['.pdf'],
        'spreadsheet': ['.xls', '.xlsx', '.csv', '.ods'],
        'presentation': ['.ppt', '.pptx', '.odp'],
        'video': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv'],
        'audio': ['.mp3', '.wav', '.ogg', '.m4a', '.flac'],
        'archive': ['.zip', '.rar', '.7z', '.tar', '.gz'],
        'code': ['.html', '.css', '.js', '.py', '.java', '.cpp', '.c', '.php', '.xml', '.json'],
    }
    
    if file_type in file_type_groups:
        extensions = file_type_groups[file_type]
        query = Q()
        for ext in extensions:
            query |= Q(file_type__iexact=ext)
        return files_queryset.filter(query)
    elif file_type.startswith('.'):
        return files_queryset.filter(file_type__iexact=file_type)
    
    return files_queryset

def filter_files_by_date(files_queryset, date_filter):
    """Filter files by date range"""
    from datetime import timedelta
    
    now = timezone.now()
    
    if date_filter == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return files_queryset.filter(uploaded_at__gte=start_date)
    elif date_filter == 'week':
        start_date = now - timedelta(days=7)
        return files_queryset.filter(uploaded_at__gte=start_date)
    elif date_filter == 'month':
        start_date = now - timedelta(days=30)
        return files_queryset.filter(uploaded_at__gte=start_date)
    elif date_filter == 'year':
        start_date = now - timedelta(days=365)
        return files_queryset.filter(uploaded_at__gte=start_date)
    
    return files_queryset

def plan_details_view(request, plan_id):
    """Show detailed plan information with appropriate buttons based on auth status"""
    try:
        plan = get_object_or_404(StoragePlan, id=plan_id, is_active=True)
        all_plans = StoragePlan.objects.filter(is_active=True).order_by('price')
        
        # Check if user is authenticated and get their current plan
        user_plan = None
        if request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.get(user=request.user)
                user_plan = user_profile.storage_plan
            except UserProfile.DoesNotExist:
                pass
        
        context = {
            'plan': plan,
            'all_plans': all_plans,
            'plans': all_plans,
            'user_plan': user_plan,  # Add user's current plan to context
            'user_is_authenticated': request.user.is_authenticated,
        }
        return render(request, 'plan_details.html', context)
    except StoragePlan.DoesNotExist:
        return redirect('register')
    

@login_required
def toggle_folder_visibility(request, folder_id):
    """Toggle folder between public and private"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            folder.is_public = not folder.is_public
            folder.save()
            
            return JsonResponse({
                'success': True, 
                'is_public': folder.is_public,
                'message': f'Folder is now {"public" if folder.is_public else "private"}'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required  
def debug_upload_issue(request):
    """Check if files are actually being uploaded"""
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    test_content = b"Test file content"
    test_file = ContentFile(test_content)
    test_path = f"debug_test/user_{request.user.id}/test.txt"
    
    try:
        saved_path = default_storage.save(test_path, test_file)
        exists = default_storage.exists(saved_path)
        size = default_storage.size(saved_path) if exists else 0
        
        if exists:
            default_storage.delete(saved_path)
        
        return JsonResponse({
            'storage_test': 'SUCCESS' if exists else 'FAILED',
            'saved_path': saved_path,
            'file_exists': exists,
            'file_size': size
        })
    except Exception as e:
        return JsonResponse({'storage_test': 'ERROR', 'error': str(e)})

@login_required
def create_folder_share_link(request, folder_id):
    """Create shareable link for folder - FIXED PASSWORD LOGIC"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            share_link = ShareLink.objects.create(folder=folder)
            
            expires_in = request.POST.get('expires_in')
            if expires_in and expires_in.isdigit():
                share_link.expires_at = timezone.now() + timezone.timedelta(days=int(expires_in))
            
            # FIXED: Simplified password logic
            enable_password = request.POST.get('enable_password') == 'on'
            password = request.POST.get('password', '').strip()
            
            print(f"🔐 Folder password protection - enabled: {enable_password}, password provided: {bool(password)}")
            
            if enable_password and password:
                share_link.set_password(password)
                print(f"✅ Password protection enabled for folder share {share_link.token}")
            else:
                share_link.require_password = False
                share_link.password_hash = None
                share_link.save()
                print(f"❌ Password protection disabled for folder share {share_link.token}")
            
            share_url = request.build_absolute_uri(f'/share/folder/{share_link.token}/')
            
            return JsonResponse({
                'success': True, 
                'share_url': share_url,
                'expires_at': share_link.expires_at.isoformat() if share_link.expires_at else None,
                'has_password': share_link.has_password()
            })
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def share_folder(request, token):
    """Handle shared folder access - FIXED PASSWORD FLOW"""
    try:
        share_link = get_object_or_404(ShareLink, token=token, is_active=True, folder__isnull=False)
        
        if share_link.expires_at and share_link.expires_at < timezone.now():
            return render(request, 'share_expired.html', {
                'error': 'This share link has expired'
            })
        
        # Check if password protection is enabled
        if share_link.has_password():
            # Check if user has verified access
            if not request.session.get(f'share_verified_{token}'):
                return render(request, 'share_password.html', {
                    'share_link': share_link,
                    'folder': share_link.folder,
                    'token': token,
                    'type': 'folder'
                })
        
        folder = share_link.folder
        
        # Get all files in the folder (including subfolders)
        files_in_folder = get_all_files_in_folder(folder)
        
        context = {
            'folder': folder,
            'files': files_in_folder,
            'share_link': share_link,
            'file_count': files_in_folder.count(),
            'share_token': token,
        }
        
        return render(request, 'share_folder.html', context)
        
    except Http404:
        return render(request, 'share_error.html', {
            'error': 'Share link not found or inactive'
        })
    except Exception as e:
        return render(request, 'share_error.html', {
            'error': f'Error accessing folder: {str(e)}'
        })

def get_all_files_in_folder(folder):
    """Get all files in folder and its subfolders recursively - EXCLUDE DELETED"""
    files = File.objects.filter(folder=folder, is_deleted=False)
    
    for subfolder in folder.subfolders.filter(is_deleted=False):
        files = files | get_all_files_in_folder(subfolder)
    
    return files

def download_shared_folder(request, token):
    """Download all files in shared folder as zip"""
    try:
        share_link = get_object_or_404(ShareLink, token=token, is_active=True, folder__isnull=False)
        
        if share_link.expires_at and share_link.expires_at < timezone.now():
            return HttpResponse("Share link has expired", status=410)
        
        folder = share_link.folder
        
        all_files = get_all_files_in_folder(folder)
        
        if not all_files.exists():
            return HttpResponse("No files to download", status=404)
        
        import zipfile
        import io
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_obj in all_files:
                try:
                    file_content = file_obj.file.read()
                    
                    file_path = file_obj.name
                    if file_obj.folder and file_obj.folder != folder:
                        relative_path = get_relative_folder_path(file_obj.folder, folder)
                        file_path = f"{relative_path}/{file_obj.name}"
                    
                    zip_file.writestr(file_path, file_content)
                except Exception as e:
                    print(f"Error adding file {file_obj.name} to zip: {e}")
                    continue
        
        zip_buffer.seek(0)
        
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{folder.name}_files.zip"'
        response['Content-Length'] = len(zip_buffer.getvalue())
        
        return response
        
    except Exception as e:
        return HttpResponse(f"Error creating download: {str(e)}", status=500)

def get_relative_folder_path(current_folder, root_folder):
    """Get relative path from root folder to current folder"""
    path_parts = []
    folder = current_folder
    
    while folder and folder != root_folder and folder.parent_folder:
        path_parts.insert(0, folder.name)
        folder = folder.parent_folder
    
    return '/'.join(path_parts)

@login_required
def move_folder_to_trash(request, folder_id):
    """Move folder to trash"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_deleted=False)
            
            # Create trash entry for the folder
            trash_item = Trash.objects.create(
                user=request.user,
                folder=folder,
                original_folder=folder.parent_folder,
                scheduled_permanent_deletion=timezone.now() + timezone.timedelta(days=30)
            )
            
            # Soft delete the folder and all its contents
            folder.is_deleted = True
            folder.deleted_at = timezone.now()
            folder.save()
            
            # Also soft delete all files in this folder
            files_in_folder = File.objects.filter(folder=folder, is_deleted=False)
            for file_obj in files_in_folder:
                file_obj.is_deleted = True
                file_obj.deleted_at = timezone.now()
                file_obj.save()
                
                # Create trash entries for files too
                Trash.objects.create(
                    user=request.user,
                    file=file_obj,
                    original_folder=folder,
                    scheduled_permanent_deletion=timezone.now() + timezone.timedelta(days=30)
                )
            
            # Recursively soft delete subfolders
            def delete_subfolders_recursive(parent_folder):
                subfolders = Folder.objects.filter(parent_folder=parent_folder, is_deleted=False)
                for subfolder in subfolders:
                    subfolder.is_deleted = True
                    subfolder.deleted_at = timezone.now()
                    subfolder.save()
                    
                    # Create trash entry for subfolder
                    Trash.objects.create(
                        user=request.user,
                        folder=subfolder,
                        original_folder=parent_folder,
                        scheduled_permanent_deletion=timezone.now() + timezone.timedelta(days=30)
                    )
                    
                    # Soft delete files in subfolder
                    files_in_subfolder = File.objects.filter(folder=subfolder, is_deleted=False)
                    for file_obj in files_in_subfolder:
                        file_obj.is_deleted = True
                        file_obj.deleted_at = timezone.now()
                        file_obj.save()
                        
                        Trash.objects.create(
                            user=request.user,
                            file=file_obj,
                            original_folder=subfolder,
                            scheduled_permanent_deletion=timezone.now() + timezone.timedelta(days=30)
                        )
                    
                    # Recursively delete deeper subfolders
                    delete_subfolders_recursive(subfolder)
            
            delete_subfolders_recursive(folder)
            
            return JsonResponse({
                'success': True,
                'message': 'Folder and its contents moved to trash'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def restore_folder(request, folder_id):
    """Restore folder from trash"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_deleted=True)
            trash_item = get_object_or_404(Trash, folder=folder, user=request.user)
            
            # Restore the folder and its contents
            folder.is_deleted = False
            folder.deleted_at = None
            folder.save()
            
            # Restore all files in this folder
            files_in_folder = File.objects.filter(folder=folder, is_deleted=True)
            for file_obj in files_in_folder:
                file_obj.is_deleted = False
                file_obj.deleted_at = None
                file_obj.save()
                
                # Delete the trash entries for these files
                file_trash_items = Trash.objects.filter(file=file_obj, user=request.user)
                file_trash_items.delete()
            
            # Recursively restore subfolders
            def restore_subfolders_recursive(parent_folder):
                subfolders = Folder.objects.filter(parent_folder=parent_folder, is_deleted=True)
                for subfolder in subfolders:
                    subfolder.is_deleted = False
                    subfolder.deleted_at = None
                    subfolder.save()
                    
                    # Delete trash entry for subfolder
                    subfolder_trash_items = Trash.objects.filter(folder=subfolder, user=request.user)
                    subfolder_trash_items.delete()
                    
                    # Restore files in subfolder
                    files_in_subfolder = File.objects.filter(folder=subfolder, is_deleted=True)
                    for file_obj in files_in_subfolder:
                        file_obj.is_deleted = False
                        file_obj.deleted_at = None
                        file_obj.save()
                        
                        file_trash_items = Trash.objects.filter(file=file_obj, user=request.user)
                        file_trash_items.delete()
                    
                    # Recursively restore deeper subfolders
                    restore_subfolders_recursive(subfolder)
            
            restore_subfolders_recursive(folder)
            
            # Delete the main folder trash entry
            trash_item.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Folder and its contents restored successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def permanent_delete_folder(request, folder_id):
    """Permanently delete folder from trash"""
    if request.method == 'POST':
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user, is_deleted=True)
            trash_item = get_object_or_404(Trash, folder=folder, user=request.user)
            
            for file in folder.files.all():
                file.file.delete(save=False)
                file.delete()
            
            for subfolder in folder.subfolders.all():
                subfolder.delete()
            
            trash_item.delete()
            folder.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Folder permanently deleted'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def verify_share_password(request, token):
    """Verify password for password-protected share links - FIXED"""
    if request.method == 'POST':
        try:
            share_link = get_object_or_404(ShareLink, token=token, is_active=True)
            
            if not share_link.has_password():
                return JsonResponse({'success': False, 'error': 'This share link is not password protected'})
            
            password = request.POST.get('password')
            if not password:
                return JsonResponse({'success': False, 'error': 'Password is required'})
            
            if share_link.check_password(password):
                # Store verification in session
                request.session[f'share_verified_{token}'] = True
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid password'})
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def is_share_verified(request, token):
    """Check if share link has been verified"""
    try:
        verified = request.session.get(f'share_verified_{token}', False)
        return JsonResponse({'verified': verified})
    except Exception as e:
        return JsonResponse({'verified': False})



@login_required
def debug_storage(request):
    """Debug view to check storage configuration"""
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    
    results = []
    
    try:
        test_content = b"Test file content"
        test_file = ContentFile(test_content)
        test_path = f"debug_test/user_{request.user.id}/test_file.txt"
        
        saved_path = default_storage.save(test_path, test_file)
        results.append(f"✅ Test file saved: {saved_path}")
        
        exists = default_storage.exists(saved_path)
        results.append(f"✅ File exists: {exists}")
        
        size = default_storage.size(saved_path)
        results.append(f"✅ File size: {size}")
        
        default_storage.delete(saved_path)
        results.append("✅ Test file cleaned up")
        
    except Exception as e:
        results.append(f"❌ Storage test failed: {e}")
    
    results.append(f"📦 Storage class: {default_storage.__class__.__name__}")
    results.append(f"📦 Bucket: {getattr(default_storage, 'bucket_name', 'N/A')}")
    results.append(f"📦 Endpoint: {getattr(default_storage, 'endpoint_url', 'N/A')}")
    
    return JsonResponse({'results': results})

@login_required
def debug_file_paths(request):
    """Debug view to check file paths"""
    files = File.objects.filter(owner=request.user, is_deleted=False)
    
    results = []
    for file_obj in files:
        results.append({
            'id': str(file_obj.id),
            'name': file_obj.name,
            'db_file_path': file_obj.file.name,
            'size': file_obj.size,
        })
    
    return JsonResponse({'files': results})



from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count, Q
from django.shortcuts import render
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from storage_app.models import UserProfile, File, Subscription, StoragePlan

@staff_member_required
def admin_dashboard(request):
    """Beautiful Admin Dashboard with all features in one page"""
    
    # User Statistics
    total_users = User.objects.count()
    new_users_today = User.objects.filter(
        date_joined__date=datetime.today()
    ).count()
    active_today = User.objects.filter(
        last_login__date=datetime.today()
    ).count()
    
    # Storage Statistics
    total_storage = UserProfile.objects.aggregate(
        Sum('used_storage')
    )['used_storage__sum'] or 0
    total_files = File.objects.count()
    
    # FIXED: Count users with PAID plans (not free)
    paid_users = UserProfile.objects.filter(
        storage_plan__plan_type__in=['basic', 'pro', 'enterprise']
    )
    paid_plans_count = paid_users.count()
    
    # FIXED: Calculate revenue from users with paid plans
    total_revenue = paid_users.aggregate(
        total_revenue=Sum('storage_plan__price')
    )['total_revenue'] or 0
    
    # Plan Distribution (All users including free)
    plan_distribution = UserProfile.objects.values(
        'storage_plan__name'
    ).annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Recent Users - Only 5
    recent_users = User.objects.select_related('userprofile').order_by('-date_joined')[:5]
    
    # Top Storage Users - Only 5
    top_storage_users = UserProfile.objects.select_related('user', 'storage_plan').order_by('-used_storage')[:5]
    
    # FIXED: Show ALL paid plans even with 0 users
    paid_plan_data = []
    paid_plans = StoragePlan.objects.filter(plan_type__in=['basic', 'pro', 'enterprise']).order_by('price')
    
    for plan in paid_plans:
        user_count = UserProfile.objects.filter(storage_plan=plan).count()
        paid_plan_data.append({
            'plan_name': plan.name,
            'plan_type': plan.plan_type,
            'price': plan.price,
            'count': user_count
        })
    
    # Debug information
    print("=== DEBUG INFORMATION ===")
    print(f"Total Users: {total_users}")
    print(f"Users with paid plans: {paid_plans_count}")
    print(f"Total Revenue: ₹{total_revenue}")
    print(f"All Paid Plans: {[(p.name, p.plan_type, p.price) for p in paid_plans]}")
    print(f"Paid Plan Data: {paid_plan_data}")

    context = {
        # Statistics
        'total_users': total_users,
        'new_users_today': new_users_today,
        'active_today': active_today,
        'total_storage': total_storage,
        'total_files': total_files,
        'active_subscriptions': paid_plans_count,
        'total_revenue': total_revenue,
        
        # Data for tables
        'recent_users': recent_users,
        'top_storage_users': top_storage_users,
        'plan_distribution': plan_distribution,
        'subscription_analytics': paid_plan_data,
    }
    
    return render(request, 'admin_dashboard.html', context)


@staff_member_required
def all_users_view(request):
    """View all registered users with pagination, search and filters"""
    users_list = User.objects.select_related('userprofile', 'userprofile__storage_plan').order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users_list = users_list.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Filter by plan type
    plan_filter = request.GET.get('plan_type', '')
    if plan_filter:
        if plan_filter == 'free':
            # Users with no storage plan OR with free plan type
            users_list = users_list.filter(
                Q(userprofile__storage_plan__isnull=True) |
                Q(userprofile__storage_plan__plan_type='free')
            )
        elif plan_filter == 'paid':
            users_list = users_list.filter(userprofile__storage_plan__plan_type__in=['basic', 'pro', 'enterprise'])
        else:
            users_list = users_list.filter(userprofile__storage_plan__plan_type=plan_filter)
    
    # Filter by active status
    active_filter = request.GET.get('active', '')
    if active_filter == 'active':
        users_list = users_list.filter(last_login__date=datetime.today())
    elif active_filter == 'inactive':
        users_list = users_list.filter(last_login__isnull=True) | users_list.filter(last_login__date__lt=datetime.today() - timedelta(days=30))
    
    total_users = users_list.count()
    
    # Pagination - show 50 users per page
    paginator = Paginator(users_list, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get plan types that actually have users
    used_plan_types = UserProfile.objects.exclude(
        storage_plan__isnull=True
    ).values_list(
        'storage_plan__plan_type', flat=True
    ).distinct()
    
    # Pass current date to template for status calculation
    current_date = datetime.now().date()
    
    context = {
        'page_obj': page_obj,
        'total_users': total_users,
        'search_query': search_query,
        'plan_filter': plan_filter,
        'active_filter': active_filter,
        'plan_types': used_plan_types,
        'current_date': current_date,  
    }
    return render(request, 'admin_all_users.html', context)

@staff_member_required
def debug_plans_view(request):
    """Debug view to check all plans and user assignments"""
    print("=== DEBUG: ALL STORAGE PLANS ===")
    all_plans = StoragePlan.objects.all()
    for plan in all_plans:
        user_count = UserProfile.objects.filter(storage_plan=plan).count()
        print(f"Plan: {plan.name} | Type: {plan.plan_type} | Price: ₹{plan.price} | Users: {user_count}")
    
    print("=== DEBUG: USERS WITH FREE PLANS ===")
    free_users = UserProfile.objects.filter(
        Q(storage_plan__isnull=True) | 
        Q(storage_plan__plan_type='free')
    )
    for profile in free_users:
        plan_name = profile.storage_plan.name if profile.storage_plan else "No Plan"
        plan_type = profile.storage_plan.plan_type if profile.storage_plan else "free"
        print(f"User: {profile.user.username} | Plan: {plan_name} | Type: {plan_type}")
    
    return HttpResponse("Check console for debug information")


@login_required
def restore_all_files(request):
    """Restore all files from trash"""
    if request.method == 'POST':
        try:
            trash_items = Trash.objects.filter(user=request.user)
            restored_count = 0
            
            for trash_item in trash_items:
                if trash_item.file:
                    file_obj = trash_item.file
                    file_obj.is_deleted = False
                    file_obj.save()
                    trash_item.delete()
                    restored_count += 1
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully restored {restored_count} files',
                'restored_count': restored_count
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    Enhanced custom password reset with additional security checks
    """
    
    def form_valid(self, form):
        user = form.user
        old_password_hash = user.password  # Store old hash for verification
        
        print(f"🔐 DEBUG: User: {user.username}")
        print(f"🔐 DEBUG: Old password hash: {old_password_hash[:50]}...")
        
        # Save the new password
        form.save()
        
        # Refresh user from database to get new password hash
        user.refresh_from_db()
        new_password_hash = user.password
        
        print(f"🔐 DEBUG: New password hash: {new_password_hash[:50]}...")
        print(f"🔐 DEBUG: Hashes match: {old_password_hash == new_password_hash}")
        
        # Verify the password was actually changed
        if user.password == old_password_hash:
            print("❌ DEBUG: Password hash didn't change!")
            from django.contrib import messages
            messages.error(self.request, 'Password change failed. Please try again.')
            return self.form_invalid(form)
        else:
            print("✅ DEBUG: Password hash changed successfully!")
        
        # Update session auth
        update_session_auth_hash(self.request, user)
        
        # Force password update in database
        user.save()
        
        # Success
        from django.contrib import messages
        messages.success(self.request, 'Password reset successful! Your old password is no longer valid.')
        
        return super().form_valid(form)
    

from django.http import JsonResponse

def clear_tab_session(request):
    """Handle tab-specific session cleanup"""
    if request.method == 'POST':
        # For tab-based sessions, we can optionally clear the server session
        print("🧹 Tab session cleanup requested")
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
def check_session_validity(request):
    """Check if session is still valid for the current tab"""
    if request.user.is_authenticated:
        return JsonResponse({'valid': True, 'username': request.user.username})
    return JsonResponse({'valid': False})    

    
def privacy_policy(request):
    return render(request, 'privacy_policy.html')

def terms_of_service(request):
    return render(request, 'terms_of_service.html')    




@staff_member_required
def admin_plans_list(request):
    """List all storage plans with management options"""
    plans = StoragePlan.objects.all().order_by('display_order', 'price')
    
    context = {
        'plans': plans,
    }
    return render(request, 'admin_plans_list.html', context)

@staff_member_required
def admin_plan_create(request):
    """Create a new storage plan"""
    if request.method == 'POST':
        form = StoragePlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f'Plan "{plan.name}" created successfully!')
            return redirect('admin_plans_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StoragePlanForm()
    
    context = {
        'form': form,
        'title': 'Create New Plan',
        'submit_text': 'Create Plan',
    }
    return render(request, 'admin_plan_form.html', context)

@staff_member_required
def admin_plan_edit(request, plan_id):
    """Edit an existing storage plan"""
    plan = get_object_or_404(StoragePlan, id=plan_id)
    
    if request.method == 'POST':
        form = StoragePlanForm(request.POST, instance=plan)
        if form.is_valid():
            updated_plan = form.save()
            messages.success(request, f'Plan "{updated_plan.name}" updated successfully!')
            return redirect('admin_plans_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Convert features list to string for textarea
        initial_data = plan.__dict__.copy()
        initial_data['features'] = ', '.join(plan.features) if plan.features else ''
        # Convert storage size to GB for display
        if plan.max_storage_size >= 1024**3:  # 1GB in bytes
            initial_data['max_storage_size'] = f"{plan.max_storage_size / (1024**3):.0f}GB"
        
        form = StoragePlanForm(instance=plan, initial=initial_data)
    
    context = {
        'form': form,
        'plan': plan,
        'title': f'Edit Plan: {plan.name}',
        'submit_text': 'Update Plan',
    }
    return render(request, 'admin_plan_form.html', context)

@staff_member_required
def admin_plan_delete(request, plan_id):
    """Delete a storage plan"""
    plan = get_object_or_404(StoragePlan, id=plan_id)
    
    if request.method == 'POST':
        plan_name = plan.name
        
        # Check if any users are using this plan
        user_count = UserProfile.objects.filter(storage_plan=plan).count()
        if user_count > 0:
            messages.error(
                request, 
                f'Cannot delete "{plan_name}" because {user_count} user(s) are currently using this plan. '
                f'Please reassign users to another plan first.'
            )
            return redirect('admin_plans_list')
        
        plan.delete()
        messages.success(request, f'Plan "{plan_name}" deleted successfully!')
        return redirect('admin_plans_list')
    
    context = {
        'plan': plan,
    }
    return render(request, 'admin_plan_confirm_delete.html', context)

@staff_member_required
def admin_plan_toggle(request, plan_id):
    """Toggle plan active status"""
    plan = get_object_or_404(StoragePlan, id=plan_id)
    
    if request.method == 'POST':
        plan.is_active = not plan.is_active
        plan.save()
        
        status = "activated" if plan.is_active else "deactivated"
        messages.success(request, f'Plan "{plan.name}" {status} successfully!')
    
    return redirect('admin_plans_list')