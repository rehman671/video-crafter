"""
URL configuration for videocrafter project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('vidvid/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('', include('apps.processors.urls')),  # Uncommented to include processors URLs
]

# Serve media files during development
if settings.DEBUG:
    # Check if we're using local storage or S3
    from django.core.files.storage import default_storage
    from storages.backends.s3boto3 import S3Boto3Storage
    
    # Only serve media files locally if we're NOT using S3
    if not isinstance(default_storage, S3Boto3Storage):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # When using S3 in DEBUG mode, files will be served directly from S3

# Add a separate pattern for temporary files
urlpatterns += static('/media/temp/', document_root=settings.BASE_DIR / 'media' / 'temp')
