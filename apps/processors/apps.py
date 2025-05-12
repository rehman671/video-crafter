from django.apps import AppConfig


class ProcessorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.processors'

    def ready(self):
        from apps.processors import signals
        
        return super().ready()