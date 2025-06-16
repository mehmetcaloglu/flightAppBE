from django.apps import AppConfig
import logging


logger = logging.getLogger(__name__)


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fleet'
    
    def ready(self):
        # start MovementManager
        try:
            from .movement_manager import movement_manager
            movement_manager.start()
            logger.info("Fleet application started, MovementManager active")
        except Exception as e:
            logger.error(f" MovementManager start error: {e}")
