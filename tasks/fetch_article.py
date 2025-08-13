from __future__ import annotations

import requests
from sqlalchemy import select

from tasks.app import celery_app
from backend.db import get_session
from backend.models import Article
from backend.text_utils import (
	canonicalize_url,
	url_hash,
	extract_readable_text,
	detect_lang,
	simhash_text,
)

headers = {
	"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=5, max_retries=3)
def fetch_article(self, url: str):
	s = get_session()
	try:
		url_c = canonicalize_url(url)
		h = url_hash(url_c)
		resp = requests.get(url, headers=headers, timeout=20)
		resp.raise_for_status()
		html = resp.text
		content = extract_readable_text(html)
		lang = detect_lang(content) if content else None
		sh = f"{simhash_text(content):x}" if content else None

		art = s.execute(select(Article).where(Article.url_hash == h)).scalars().first()
		if not art:
			art = s.execute(select(Article).where(Article.url == url)).scalars().first()
		if art:
			art.url_canonical = url_c
			art.url_hash = h
			if content:
				art.content = content
				art.content_simhash = sh
			if lang:
				art.lang = lang
			s.commit()
			return art.id
	finally:
		s.close()
