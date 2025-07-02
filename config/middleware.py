# middleware.py
import traceback
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class S3DebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            if "This backend doesn't support absolute paths" in str(e):
                logger.error("S3 absolute path error detected!", exc_info=True)
                # Get full stack trace
                tb = traceback.format_exc()
                logger.error(f"Full traceback:\n{tb}")
            raise


from django.http import HttpResponse
from django.conf import settings

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow admin panel
        if request.path.startswith('/vidvid/'):
            return self.get_response(request)
        
        # Block everything else
        return HttpResponse(
            "Service temporarily unavailable for maintenance", 
            status=503,
            content_type="text/plain"
        )



class RequestInfoMiddleware(MiddlewareMixin):
    def process_request(self, request):
        ip = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        method = request.method
        path = request.path

        print(f"[Request Info] IP: {ip}, Method: {method}, Path: {path}, User-Agent: {user_agent}")

    def get_client_ip(self, request):
        """Get client IP even if behind reverse proxy like Nginx"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
