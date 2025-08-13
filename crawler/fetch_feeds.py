from __future__ import annotations

import os
from datetime import datetime
from time import mktime
from typing import Dict, List

import feedparser
import requests
from backend.text_utils import canonicalize_url, url_hash
from urllib.parse import urlparse
import ssl

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5050")

# Set a realistic user-agent so some sites don't block requests
REQUEST_HEADERS = {
	"User-Agent": (
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
		"AppleWebKit/537.36 (KHTML, like Gecko) "
		"Chrome/126.0 Safari/537.36"
	),
}

FEEDS = [
	{"url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "source": "BBC Technology", "category": "technology"},
	{"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC World", "category": "world"},
	{"url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "source": "NYTimes Technology", "category": "technology"},
	{"url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "source": "NYTimes World", "category": "world"},
	{"url": "https://www.theguardian.com/world/rss", "source": "The Guardian World", "category": "world"},
	{"url": "https://www.theguardian.com/uk/technology/rss", "source": "The Guardian Technology", "category": "technology"},
	{"url": "https://feeds.arstechnica.com/arstechnica/index", "source": "Ars Technica", "category": "technology"},
	{"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "category": "world"},
# Hong Kong sources (tag with country hk; keep category topical not "hongkong")
{"url": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml", "source": "RTHK 即時本地", "category": "local", "country": "hk"},
{"url": "https://www.scmp.com/rss/91/feed", "source": "SCMP Hong Kong", "category": "local", "country": "hk"},
{"url": "https://hongkongfp.com/feed/", "source": "Hong Kong Free Press", "category": "local", "country": "hk"},
{"url": "https://news.mingpao.com/rss/ins/all.xml", "source": "明報 即時", "category": "local", "country": "hk"},
{"url": "https://www.thestandard.com.hk/rss/instant-news/", "source": "The Standard 即時", "category": "local", "country": "hk"},
{"url": "https://news.now.com/rss/local", "source": "Now News 本地", "category": "local", "country": "hk"},
{"url": "https://www.hk01.com/rss", "source": "HK01", "category": "local", "country": "hk"},
    # Additional general/tech/business/international sources
    {"url": "https://feeds.skynews.com/feeds/rss/world.xml", "source": "Sky News World", "category": "world"},
    {"url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "source": "WSJ World", "category": "world"},
    {"url": "https://www.economist.com/finance-and-economics/rss.xml", "source": "The Economist Finance", "category": "economy"},
    {"url": "https://www.ft.com/world/asia-pacific/rss", "source": "Financial Times APAC", "category": "economy"},
    {"url": "https://apnews.com/hub/apf-topnews?utm_source=apnews.com&utm_medium=referral&utm_campaign=rss&output=rss", "source": "AP News", "category": "general"},
    {"url": "https://www.reuters.com/world/asia-pacific/rss", "source": "Reuters APAC", "category": "world"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "source": "CNBC Top News", "category": "business"},
    {"url": "https://www.bloomberg.com/feeds/podcast/etf-report.xml", "source": "Bloomberg", "category": "economy"},
    {"url": "https://feeds.feedburner.com/Techcrunch", "source": "TechCrunch", "category": "technology"},
    {"url": "https://www.theverge.com/rss/index.xml", "source": "The Verge", "category": "technology"},
    # Regional Asia
    {"url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "source": "CNA", "category": "world", "country": "sg"},
    {"url": "https://japantoday.com/feed", "source": "Japan Today", "category": "world", "country": "jp"},
]


def parse_feed(feed_conf: Dict[str, str]) -> List[Dict[str, str]]:
	# Build SSL context that uses system CA; as a fallback, allow unverified if needed
	context = None
	try:
		context = ssl.create_default_context()
	except Exception:
		context = None
	# feedparser doesn't accept ssl_context directly; open the URL with requests and feed content
	try:
		resp = requests.get(feed_conf["url"], headers=REQUEST_HEADERS, timeout=30)
		resp.raise_for_status()
		content = resp.content
	except Exception as e:
		print("HTTP error fetching feed", feed_conf.get("url"), e)
		return []
	parsed = feedparser.parse(content)
	items: List[Dict[str, str]] = []
	for entry in parsed.entries:
		title = getattr(entry, "title", None) or ""
		link = getattr(entry, "link", None) or ""
		summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
		published_at = None
		if getattr(entry, "published_parsed", None):
			try:
				published_at = datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
			except Exception:
				published_at = None
		# Infer country from config or URL
		country = feed_conf.get("country")
		def infer_country(url: str) -> str | None:
			if not url:
				return None
			host = urlparse(url).hostname or ""
			host = host.lower()
			# prioritized suffix mapping
			suffix_map = {
				".com.hk": "hk",
				".org.hk": "hk",
				".gov.hk": "hk",
				".co.uk": "gb",
				".com.au": "au",
				".com.sg": "sg",
				".co.jp": "jp",
				".com.tw": "tw",
				".com.cn": "cn",
			}
			for suf, code in suffix_map.items():
				if host.endswith(suf):
					return code
			# TLD mapping
			tld_map = {
				"hk":"hk","uk":"gb","us":"us","cn":"cn","jp":"jp","kr":"kr","sg":"sg","tw":"tw",
				"my":"my","th":"th","vn":"vn","ph":"ph","id":"id","au":"au","ca":"ca","de":"de",
				"fr":"fr","it":"it","es":"es"
			}
			parts = host.rsplit('.', 1)
			if len(parts) == 2:
				return tld_map.get(parts[1])
			return None

		if not country:
			country = infer_country(link) or infer_country(feed_conf.get("url", ""))
		items.append({
			"title": title,
			"url": canonicalize_url(link) if link else link,
			"summary": summary,
			"source": feed_conf.get("source"),
			"category": feed_conf.get("category"),
			"published_at": published_at,
			"country": country,
		})
	# If feed had an error, log basic info
	if getattr(parsed, "bozo", 0):
		print("Warning: bozo feed:", feed_conf.get("url"), getattr(parsed, "bozo_exception", None))
	return items


def ingest(items: List[Dict[str, str]]) -> None:
	if not items:
		return
	resp = requests.post(f"{BACKEND_URL}/articles/bulk", json={"items": items}, timeout=30)
	resp.raise_for_status()
	print("Ingested:", resp.json())


def main():
	all_items: List[Dict[str, str]] = []
	for f in FEEDS:
		try:
			items = parse_feed(f)
			all_items.extend(items)
		except Exception as e:
			print("Error parsing feed", f.get("url"), e)
	# Dedupe by URL to avoid DB unique constraint conflicts
	if all_items:
		seen = set()
		deduped: List[Dict[str, str]] = []
		for it in all_items:
			url = (it.get("url") or "").strip()
			if not url or url in seen:
				continue
			seen.add(url)
			deduped.append(it)
		all_items = deduped
		try:
			ingest(all_items)
		except Exception as e:
			print("Error ingesting:", e)


if __name__ == "__main__":
	main()
