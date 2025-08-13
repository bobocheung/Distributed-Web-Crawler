from __future__ import annotations

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery('news', broker=REDIS_URL, backend=REDIS_URL)

# Basic config; production 可再細化
celery_app.conf.task_acks_late = True
celery_app.conf.worker_max_tasks_per_child = 100

# Beat schedule: fetch feeds every 15 minutes
celery_app.conf.timezone = 'UTC'
celery_app.conf.beat_schedule = {
    'fetch-feeds-every-15m': {
        'task': 'tasks.schedule.schedule_feeds',
        'schedule': crontab(minute='*/15'),
    }
}
