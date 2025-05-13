from django.urls import path, include

from apps.core.views import (
    index, subscribe, register_after_payment, preview, user_logout, 
    user_login, scene_view, download_video, manage_subscription, 
    stripe_billing_portal, purchase_credits, credits_success, stripe_webhook,
    upgrade_plan, asset_view, delete_asset, rename_asset, verify_email,
    register_view, register, password_reset_request, password_reset_confirm, loading_view, proxy_video_download,
    cancel_subscription
)

urlpatterns = [
   path("", index, name="index"),
   path("subscribe/<int:plan_id>/", subscribe, name="subscribe"),
   path("register-after-payment/", register_after_payment, name="register_after_payment"),
   path("preview/", preview, name="preview"),
   path("logout/", user_logout, name="logout"),
   path("login/", user_login, name="login"),
   path("scene/<int:video_id>/", scene_view, name="scene_view"),

   path("download/<int:video_id>/", download_video, name="download_video"),
   path("download-file/<int:video_id>/", proxy_video_download, name="proxy_video_download"),

   # HAVE TO CHANGE 
   path("password_reset/", index, name="password_reset"),
   path("manage_subscription/", manage_subscription, name="manage_subscription"),  # Add this URL pattern
#    path("asset_library", index, name="asset_library"),
#    path("recent_videos", index, name="recent_videos"),  
 path("billing_portal/", stripe_billing_portal, name="billing_portal"),  # Add this URL pattern
   path("upgrade-plan/<int:plan_id>/", upgrade_plan, name="upgrade_plan"),  # Add plan upgrade URL
   path("cancel-subscription/", cancel_subscription, name="cancel_subscription"),  # Add subscription cancellation URL
   
   # Credit purchase URLs
   path("accounts/add-credits", purchase_credits, name="purchase_credits"),
   path("accounts/credits-success", credits_success, name="credits_success"),
   
   # Stripe webhook
   path("webhook/", stripe_webhook, name="stripe_webhook"),
   path("asset-library/", asset_view, name="asset_library"),
   path("delete-asset/<int:asset_id>/", delete_asset, name="delete_asset"),  # Add asset deletion URL
   path("rename-asset/<int:asset_id>/", rename_asset, name="rename_asset"),  # Add asset rename URL
       path('verify-email/<str:uidb64>/<str:token>/', verify_email, name='verify-email'),

    path('register/', register_view, name='register'),

    path("register/", register, name="register"),
    path('password-reset/', password_reset_request, name='password_reset_request'),
    path('password-reset/<uidb64>/<token>/', password_reset_confirm, name='password_reset_confirm'),
    path('loading/<int:video_id>/', loading_view, name='loading'),  # Add loading URL pattern

]
