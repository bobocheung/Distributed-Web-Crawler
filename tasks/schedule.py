from __future__ import annotations

from tasks.app import celery_app
from crawler.fetch_feeds import FEEDS, SUPPLEMENTAL_FEEDS, SUPPLEMENTAL_FEEDS_LANG
from tasks.fetch_feed import fetch_feed
import requests

@celery_app.task
def schedule_feeds() -> int:
	count = 0
	for f in FEEDS:
		url = f["url"] if isinstance(f, dict) else f
		fetch_feed.delay(url)
		count += 1
	# quota balancer: ensure minimum counts per country/lang in last 24h
	try:
		resp = requests.get("http://web:5000/crawl_stats", timeout=10)
		stats = resp.json().get("last24h", {})
		min_per_country = 20
		by_country = { (i.get("country") or ""): i.get("count", 0) for i in (stats.get("by_country") or []) }
		for code, cfgs in SUPPLEMENTAL_FEEDS.items():
			c = code.split(":",1)[1]
			if by_country.get(c, 0) < min_per_country:
				for sup in cfgs:
					fetch_feed.delay(sup["url"])
					count += 1
		# language quotas
		min_per_lang = 20
		by_lang = { (i.get("lang") or ""): i.get("count", 0) for i in (stats.get("by_lang") or []) }
		for code, cfgs in SUPPLEMENTAL_FEEDS_LANG.items():
			l = code.split(":",1)[1]
			if by_lang.get(l, 0) < min_per_lang:
				for sup in cfgs:
					fetch_feed.delay(sup["url"])
					count += 1
	except Exception:
		pass
	return count
