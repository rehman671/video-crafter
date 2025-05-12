import logging
from celery import shared_task
from .utils import cleanup_old_assets

logger = logging.getLogger(__name__)

@shared_task(name='cleanup_old_assets_task')
def cleanup_old_assets_task(days=1):
    """
    Celery task to clean up assets older than the specified number of days.
    
    Args:
        days: Number of days to keep assets (default: 1)
    """
    logger.info(f"Starting cleanup of assets older than {days} days")
    result = cleanup_old_assets(days=days)
    
    logger.info(f"Cleanup completed. Deleted {result['deleted_count']} files.")
    if result['errors']:
        logger.warning(f"Encountered {len(result['errors'])} errors during cleanup.")
        
    return result
