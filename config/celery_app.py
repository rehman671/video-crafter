import os
from celery import Celery
from dotenv import load_dotenv
from celery.schedules import crontab

# Load environment variables from .env file
load_dotenv()

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('videocrafter')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Beat schedule
app.conf.beat_schedule = {
    # Add the cleanup task to run every 2 hours
    'cleanup-old-assets': {
        'task': 'cleanup_old_assets_task',
        'schedule': 3600 * 2,  # Run every 2 hours (3600 seconds * 2)
        'args': (1,),  # Delete files older than 1 day
    },
    # Add the local file cleanup task to run every hour
    'cleanup-local-files': {
        'task': 'cleanup_local_files_task',
        'schedule': 3600,  # Run every hour (3600 seconds)
        'args': (),
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
