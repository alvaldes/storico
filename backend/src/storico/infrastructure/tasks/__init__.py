"""Celery application for Storico background tasks.

The worker is started via::

    celery -A storico.infrastructure.tasks worker --loglevel=info

For Aiven Redis with SSL (``rediss://``), the broker URL is configured
in ``settings.celery_broker_url`` (env var ``STORICO_CELERY_BROKER_URL``).
"""

from celery import Celery

from storico.config.settings import Settings

settings = Settings.load()

celery_app = Celery(
    "storico",
    broker=settings.celery_broker_url,
    include=["storico.infrastructure.tasks.extraction_task"],
)

# Optional: configure Celery behaviour
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

__all__ = ["celery_app"]
