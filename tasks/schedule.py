from __future__ import annotations

from tasks.app import celery_app
from crawler.fetch_feeds import FEEDS
from tasks.fetch_feed import fetch_feed

@celery_app.task
def schedule_feeds() -> int:
	count = 0
	for f in FEEDS:
		url = f["url"] if isinstance(f, dict) else f
		fetch_feed.delay(url)
		count += 1
	return count
