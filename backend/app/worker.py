from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "slrms",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    include=["app.tasks.document_processing"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": settings.DOCUMENT_TASK_TIMEOUT_SECONDS + 300},
    task_track_started=True,
)
