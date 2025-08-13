from __future__ import annotations

from tasks.app import celery_app
from crawler.fetch_feeds import parse_feed, ingest
from tasks.fetch_article import fetch_article

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=5, max_retries=5)
def fetch_feed(self, feed_url: str):
	items = parse_feed({"url": feed_url, "source": None, "category": None})
	if items:
		ingest(items)
		# chain: 對每篇文章抓取全文內容
		for it in items:
			url = (it.get("url") or "").strip()
			if url:
				fetch_article.delay(url)
	return len(items)
