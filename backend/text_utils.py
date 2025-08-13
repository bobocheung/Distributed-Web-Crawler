from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup
import langid
from simhash import Simhash


def canonicalize_url(url: str) -> str:
	try:
		u = urllib.parse.urlsplit(url)
		q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
		q = [(k, v) for k, v in q if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
		q.sort()
		new = urllib.parse.urlunsplit((u.scheme, u.netloc.lower(), u.path.rstrip("/"), urllib.parse.urlencode(q), ""))
		return new
	except Exception:
		return url


def url_hash(url: str) -> str:
	return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def normalize_source(name: Optional[str]) -> Optional[str]:
	if not name:
		return name
	return re.sub(r"\s+", " ", name.strip()).lower()


def extract_readable_text(html: str) -> str:
	soup = BeautifulSoup(html, "html.parser")
	for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
		tag.decompose()
	texts = []
	for p in soup.find_all(["p", "article", "section", "div"]):
		t = p.get_text(" ", strip=True)
		if t and len(t) > 80:
			texts.append(t)
	return "\n\n".join(texts)[:20000]


def detect_lang(text: str) -> str:
	try:
		lang, _ = langid.classify(text[:4000])
		return lang
	except Exception:
		return "und"


def simhash_text(text: str) -> int:
	return Simhash(text.split()).value


def infer_country_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        host = (urllib.parse.urlsplit(url).hostname or '').lower()
    except Exception:
        return None
    suffix_map = {
        '.com.hk': 'hk', '.org.hk': 'hk', '.gov.hk': 'hk',
        '.co.uk': 'gb', '.com.au': 'au', '.com.sg': 'sg', '.co.jp': 'jp',
        '.com.tw': 'tw', '.com.cn': 'cn'
    }
    for suf, code in suffix_map.items():
        if host.endswith(suf):
            return code
    tld_map = {
        'hk':'hk','uk':'gb','us':'us','cn':'cn','jp':'jp','kr':'kr','sg':'sg','tw':'tw',
        'my':'my','th':'th','vn':'vn','ph':'ph','id':'id','au':'au','ca':'ca','de':'de',
        'fr':'fr','it':'it','es':'es','gb':'gb'
    }
    parts = host.rsplit('.', 1)
    if len(parts) == 2:
        return tld_map.get(parts[1])
    return None
