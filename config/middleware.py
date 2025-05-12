# middleware.py
import traceback
import logging

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