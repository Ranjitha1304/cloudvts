from django.urls import path
from . import views
from django.contrib.admin.views.decorators import staff_member_required

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    # Main pages
    path('dashboard/', views.dashboard, name='dashboard'),
    path('files/', views.file_list, name='file_list'),
    path('files/folder/<uuid:folder_id>/', views.file_list, name='file_list_folder'),
    path('files/starred/', views.starred_files, name='starred_files'),
    
    # File operations
    path('upload/', views.upload_file, name='upload_file'),
    path('files/<uuid:file_id>/download/', views.download_file, name='download_file'),
    path('file/preview/<uuid:file_id>/', views.preview_file, name='preview_file'),
    
    # File actions
    path('file/star/<uuid:file_id>/', views.toggle_star_file, name='toggle_star_file'),
    path('folder/star/<uuid:folder_id>/', views.toggle_star_folder, name='toggle_star_folder'),
    path('file/toggle-public/<uuid:file_id>/', views.toggle_file_visibility, name='toggle_file_visibility'),
    
    # Folder operations
    path('folder/create/', views.create_folder, name='create_folder'),
    path('folder/delete/<uuid:folder_id>/', views.delete_folder, name='delete_folder'),
    path('file/move/<uuid:file_id>/', views.move_file, name='move_file'),
    
    # Sharing
    path('share/create/<uuid:file_id>/', views.create_share_link, name='create_share'),
    path('share/<uuid:token>/', views.share_file, name='share_file'),
    path('public/file/<uuid:file_id>/', views.public_file_access, name='public_file_access'),
    
    # Trash management
    path('trash/', views.trash_view, name='trash_view'),
    path('file/move-to-trash/<uuid:file_id>/', views.move_to_trash, name='move_to_trash'),
    path('file/restore/<uuid:file_id>/', views.restore_file, name='restore_file'),
    path('file/permanent-delete/<uuid:file_id>/', views.permanent_delete_file, name='permanent_delete_file'),
    path('file/empty-trash/', views.empty_trash, name='empty_trash'),
    path('file/restore-all/', views.restore_all_files, name='restore_all_files'),
    
    # Payments & Plans
    path('pricing/', views.pricing_plans, name='pricing_plans'),
    path('create-checkout-session/<str:plan_id>/', views.create_checkout_session, name='create_checkout_session'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),
    path('subscription/', views.subscription_management, name='subscription_management'),
    path('subscription/cancel/', views.cancel_subscription, name='cancel_subscription'),
    
    # Utility
    path('dashboard/toggle-view/', views.toggle_dashboard_view, name='toggle_dashboard_view'),

    path('plan-details/<int:plan_id>/', views.plan_details_view, name='plan_details'),

    path('folder/toggle-public/<uuid:folder_id>/', views.toggle_folder_visibility, name='toggle_folder_visibility'),

    path('debug-storage/', views.debug_storage, name='debug_storage'),

    path('debug-files/', views.debug_file_paths, name='debug_files'),

    path('debug-upload-issue/', views.debug_upload_issue, name='debug_upload_issue'),

    path('share/folder/create/<uuid:folder_id>/', views.create_folder_share_link, name='create_folder_share'),
    path('share/folder/<uuid:token>/', views.share_folder, name='share_folder'),

    path('folder/move-to-trash/<uuid:folder_id>/', views.move_folder_to_trash, name='move_folder_to_trash'),
    path('folder/restore/<uuid:folder_id>/', views.restore_folder, name='restore_folder'),
    path('folder/permanent-delete/<uuid:folder_id>/', views.permanent_delete_folder, name='permanent_delete_folder'),
    path('share/folder/download/<str:token>/', views.download_shared_folder, name='download_shared_folder'),

    path('share/verify-password/<uuid:token>/', views.verify_share_password, name='verify_share_password'),
    path('share/is-verified/<uuid:token>/', views.is_share_verified, name='is_share_verified'),

    path('admin-dashboard/', staff_member_required(views.admin_dashboard), name='admin_dashboard'),
    path('admin-dashboard/all-users/', views.all_users_view, name='all_users'),

    path('admin-debug-plans/', views.debug_plans_view, name='debug_plans'),

    path('clear-tab-session/', views.clear_tab_session, name='clear_tab_session'),
    path('check-session/', views.check_session_validity, name='check_session_validity'),

    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('terms-of-service/', views.terms_of_service, name='terms_of_service'),


    # Plan Management URLs
    path('admin-dashboard/plans/', views.admin_plans_list, name='admin_plans_list'),
    path('admin-dashboard/plans/create/', views.admin_plan_create, name='admin_plan_create'),
    path('admin-dashboard/plans/<int:plan_id>/edit/', views.admin_plan_edit, name='admin_plan_edit'),
    path('admin-dashboard/plans/<int:plan_id>/delete/', views.admin_plan_delete, name='admin_plan_delete'),
    path('admin-dashboard/plans/<int:plan_id>/toggle/', views.admin_plan_toggle, name='admin_plan_toggle'),




]