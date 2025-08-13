from __future__ import annotations

import os
from datetime import datetime
from time import mktime
from typing import Dict, List

import feedparser
import requests
from backend.text_utils import canonicalize_url, url_hash
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import ssl
import json

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:5050")

# Set a realistic user-agent so some sites don't block requests
REQUEST_HEADERS = {
	"User-Agent": (
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
		"AppleWebKit/537.36 (KHTML, like Gecko) "
		"Chrome/126.0 Safari/537.36"
	),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

# domain-specific header hints
HEADERS_BY_DOMAIN = {
    "timesofisrael.com": {"Accept-Language": "en-US,en;q=0.9"},
    "thejakartapost.com": {"Accept-Language": "en-US,en;q=0.9"},
    "apnews.com": {"Accept-Language": "en-US,en;q=0.9"},
    "reuters.com": {"Accept-Language": "en-US,en;q=0.9"},
}

ALT_FEEDS = {
    # domain -> list of preferred alternate feed or HTML pages to derive feeds from
    "washingtonpost.com": [
        "https://feeds.washingtonpost.com/rss/world",
    ],
    "thejakartapost.com": [
        "https://www.thejakartapost.com/",
    ],
    "timesofisrael.com": [
        "https://www.timesofisrael.com/",
    ],
    "alarabiya.net": [
        "https://english.alarabiya.net/",
    ],
}

# collect failures for reporting
FAILED: List[Dict[str, str]] = []

def _headers_for(url: str) -> Dict[str, str]:
    headers = dict(REQUEST_HEADERS)
    try:
        host = urlparse(url).hostname or ""
        headers.update(HEADERS_BY_DOMAIN.get(host, {}))
        headers["Referer"] = f"https://{host}/"
    except Exception:
        pass
    return headers

def _fetch_content(url: str) -> bytes | None:
    headers = _headers_for(url)
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.content
    except requests.HTTPError as e:
        code = getattr(e.response, 'status_code', None)
        if code in (401,403,404):
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            try:
                r = requests.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                return r.content
            except Exception:
                host = urlparse(url).hostname or ""
                for dom, alts in ALT_FEEDS.items():
                    if host.endswith(dom):
                        for alt in (alts if isinstance(alts, list) else [alts]):
                            try:
                                rr = requests.get(alt, headers=headers, timeout=30)
                                rr.raise_for_status()
                                return rr.content
                            except Exception:
                                continue
        FAILED.append({"url": url, "reason": f"http_error:{code}"})
        return None
    except Exception:
        FAILED.append({"url": url, "reason": "exception"})
        return None

def _discover_feed_from_html(url: str) -> str | None:
    try:
        html = _fetch_content(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("link", rel=lambda x: x and "alternate" in x):
            t = (link.get("type") or "").lower()
            if "rss" in t or "atom" in t or "xml" in t:
                href = link.get("href")
                if href:
                    return requests.compat.urljoin(url, href)
        for path in ("/feed", "/rss", "/rss.xml", "/index.xml", "/atom.xml"):
            test = requests.compat.urljoin(url, path)
            content = _fetch_content(test)
            if content and feedparser.parse(content).entries:
                return test
        return None
    except Exception:
        return None

def _simple_html_to_items(html: bytes, feed_conf: Dict[str, str]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a[href]")[:50]:
            title = (a.get_text() or "").strip()
            href = a.get("href")
            if not title or not href:
                continue
            href = requests.compat.urljoin(feed_conf.get("url", ""), href)
            href = canonicalize_url(href)
            items.append({
                "title": title[:200],
                "url": href,
                "summary": None,
                "source": feed_conf.get("source"),
                "category": feed_conf.get("category"),
                "published_at": None,
                "country": feed_conf.get("country"),
            })
            if len(items) >= 20:
                break
    except Exception:
        return []
    return items

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
    {"url": "https://feeds.reuters.com/reuters/worldNews", "source": "Reuters World", "category": "world"},
    {"url": "https://apnews.com/hub/apf-topnews?utm_source=apnews.com&utm_medium=referral&utm_campaign=rss&output=rss", "source": "AP News", "category": "general"},
    {"url": "https://www.reuters.com/world/asia-pacific/rss", "source": "Reuters APAC", "category": "world"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "source": "CNBC Top News", "category": "business"},
    # remove unstable Bloomberg podcast feed
    {"url": "https://feeds.feedburner.com/Techcrunch", "source": "TechCrunch", "category": "technology"},
    {"url": "https://www.theverge.com/rss/index.xml", "source": "The Verge", "category": "technology"},
    # North America regional
    {"url": "https://www.cbc.ca/webfeed/rss/rss-topstories", "source": "CBC Canada", "category": "world", "country": "ca"},
    {"url": "https://www.ctvnews.ca/rss/ctvnews-ca-canada-public-rss-1.822295", "source": "CTV Canada", "category": "world", "country": "ca"},
    {"url": "https://www.ctvnews.ca/rss/ctvnews-ca-world-public-rss-1.822289", "source": "CTV World", "category": "world", "country": "ca"},
    {"url": "https://www.theglobeandmail.com/arc/outboundfeeds/rss/?outputType=xml", "source": "The Globe and Mail", "category": "world", "country": "ca"},
    {"url": "https://globalnews.ca/feed/", "source": "Global News Canada", "category": "world", "country": "ca"},
    # Europe
    {"url": "https://www.bbc.co.uk/news/uk/rss.xml", "source": "BBC UK", "category": "world", "country": "gb"},
    {"url": "https://www.thelocal.fr/feeds/rss.php", "source": "The Local France", "category": "world", "country": "fr"},
    {"url": "https://www.thelocal.de/feeds/rss.php", "source": "The Local Germany", "category": "world", "country": "de"},
    {"url": "https://www.lemonde.fr/rss/une.xml", "source": "Le Monde", "category": "world", "country": "fr"},
    {"url": "https://newsfeed.zeit.de/index", "source": "Die Zeit", "category": "world", "country": "de"},
    # Australia / New Zealand
    {"url": "https://www.theguardian.com/au/rss", "source": "The Guardian AU", "category": "world", "country": "au"},
    {"url": "https://www.theguardian.com/world/newzealand/rss", "source": "The Guardian NZ", "category": "world", "country": "nz"},
    {"url": "https://www.abc.net.au/news/feed/51120/rss.xml", "source": "ABC Australia", "category": "world", "country": "au"},
    {"url": "https://www.rnz.co.nz/rss", "source": "RNZ", "category": "world", "country": "nz"},
    # Japan / Korea
    {"url": "https://www3.nhk.or.jp/nhkworld/en/news/rss/", "source": "NHK World", "category": "world", "country": "jp"},
    {"url": "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "source": "Asahi Shimbun", "category": "world", "country": "jp"},
    {"url": "https://www.koreaherald.com/rss/0201.xml", "source": "Korea Herald", "category": "world", "country": "kr"},
    {"url": "https://asia.nikkei.com/rss/feed/nar", "source": "Nikkei Asia", "category": "world", "country": "jp"},
    {"url": "https://www.straitstimes.com/news/world/rss.xml", "source": "Straits Times World", "category": "world", "country": "sg"},
    # Singapore / Taiwan / HK (int'l)
    {"url": "https://www.todayonline.com/feed", "source": "TODAY SG", "category": "world", "country": "sg"},
    {"url": "https://www.taipeitimes.com/rss/front", "source": "Taipei Times", "category": "world", "country": "tw"},
    {"url": "https://www.scmp.com/rss/2/feed", "source": "SCMP International", "category": "world", "country": "hk"},
    # Spain / Italy / Germany (extra)
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "world", "country": "es"},
    {"url": "https://www.ansa.it/sito/ansait_rss.xml", "source": "ANSA", "category": "world", "country": "it"},
    {"url": "https://rss.dw.com/rdf/rss-en-all", "source": "DW (EN)", "category": "world", "country": "de"},
    # USA general/tech/business
    {"url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml", "source": "WSJ Business", "category": "business", "country": "us"},
    {"url": "https://www.washingtonpost.com/rss/world/", "source": "Washington Post World", "category": "world", "country": "us"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "source": "NYTimes Business", "category": "business", "country": "us"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "source": "NYTimes Science", "category": "science", "country": "us"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "source": "NYTimes Technology", "category": "technology", "country": "us"},
    {"url": "https://www.theverge.com/rss/index.xml", "source": "The Verge", "category": "technology", "country": "us"},
    {"url": "https://www.wired.com/feed/rss", "source": "WIRED", "category": "technology", "country": "us"},
    {"url": "https://feeds.arstechnica.com/arstechnica/index", "source": "Ars Technica", "category": "technology", "country": "us"},
    # UK
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml", "source": "BBC Business", "category": "business", "country": "gb"},
    {"url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "source": "BBC Science", "category": "science", "country": "gb"},
    # Canada
    {"url": "https://financialpost.com/feed/", "source": "Financial Post", "category": "finance", "country": "ca"},
    {"url": "https://www.theglobeandmail.com/arc/outboundfeeds/rss/?outputType=xml", "source": "The Globe and Mail", "category": "world", "country": "ca"},
    # France / Germany / Italy / Spain add tech/business
    {"url": "https://www.lemonde.fr/technologies/rss_full.xml", "source": "Le Monde Tech", "category": "technology", "country": "fr"},
    {"url": "https://www.lefigaro.fr/rss/figaro_technologies.xml", "source": "Le Figaro Tech", "category": "technology", "country": "fr"},
    {"url": "https://www.handelsblatt.com/contentexport/feed/top-themen", "source": "Handelsblatt", "category": "economy", "country": "de"},
    {"url": "https://www.repubblica.it/rss/tecnologia/rss2.0.xml", "source": "La Repubblica Tech", "category": "technology", "country": "it"},
    {"url": "https://elpais.com/tecnologia/rss/", "source": "El País Tecnologia", "category": "technology", "country": "es"},
    # Japan / Korea tech/business
    {"url": "https://www.japantimes.co.jp/feed/technology.rss", "source": "Japan Times Tech", "category": "technology", "country": "jp"},
    {"url": "https://rss.japantimes.co.jp/rss/feed/top_news.rss", "source": "Japan Times Top", "category": "world", "country": "jp"},
    {"url": "https://www.koreatimes.co.kr/www/rss/nation.xml", "source": "Korea Times Nation", "category": "world", "country": "kr"},
    # SG / TW / MY / TH / VN / PH / ID tech/general
    {"url": "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "source": "CNA", "category": "world", "country": "sg"},
    {"url": "https://www.techinasia.com/feed", "source": "Tech in Asia", "category": "technology", "country": "sg"},
    {"url": "https://feeds.feedburner.com/ithome/it", "source": "iThome", "category": "technology", "country": "tw"},
    {"url": "https://www.ithome.com.tw/rss", "source": "iThome TW", "category": "technology", "country": "tw"},
    {"url": "https://www.cna.com.tw/list/rsoc.aspx", "source": "中央社 社會", "category": "general", "country": "tw"},
    {"url": "https://www.themalaysianinsight.com/rss/", "source": "Malaysian Insight", "category": "world", "country": "my"},
    {"url": "https://www.bangkokpost.com/rss/data/topstories.xml", "source": "Bangkok Post", "category": "world", "country": "th"},
    {"url": "https://e.vnexpress.net/rss", "source": "VnExpress", "category": "world", "country": "vn"},
    {"url": "https://www.gmanetwork.com/news/rss/news/", "source": "GMA News", "category": "world", "country": "ph"},
    {"url": "https://www.thejakartapost.com/rss", "source": "Jakarta Post", "category": "world", "country": "id"},
    # Middle East
    {"url": "https://english.alarabiya.net/.mrss/en/english.xml", "source": "Al Arabiya", "category": "world", "country": "sa"},
    {"url": "https://www.timesofisrael.com/feed/", "source": "Times of Israel", "category": "world", "country": "il"},
    # HK 補強科技/財經
    {"url": "https://www.hket.com/rss.xml", "source": "經濟日報", "category": "economy", "country": "hk"},
    {"url": "https://finance.now.com/news/rss/finance_rss.xml", "source": "Now 財經", "category": "finance", "country": "hk"},
    {"url": "https://unwire.hk/feed/", "source": "Unwire.hk", "category": "technology", "country": "hk"},
    # HK 其他主要媒體（若無 RSS 由自動發現/HTML 備援處理）
    {"url": "https://www.singtao.com/", "source": "星島日報", "category": "local", "country": "hk"},
    {"url": "https://www.on.cc/", "source": "東方日報", "category": "local", "country": "hk"},
    {"url": "https://www.hkej.com/", "source": "信報財經新聞", "category": "finance", "country": "hk"},
    {"url": "https://www.hkcd.com.hk/", "source": "香港商報", "category": "local", "country": "hk"},
    {"url": "https://www.singpao.com.hk/", "source": "成報", "category": "local", "country": "hk"},
    {"url": "https://www.am730.com.hk/", "source": "AM730", "category": "local", "country": "hk"},
    {"url": "https://www.inmediahk.net/", "source": "香港獨立媒體", "category": "local", "country": "hk"},
    {"url": "https://hk.news.yahoo.com/", "source": "Yahoo 香港新聞", "category": "general", "country": "hk"},
    {"url": "https://www.orangenews.hk/", "source": "橙新聞", "category": "general", "country": "hk"},
    {"url": "https://www.bastillepost.com/hongkong", "source": "巴士的報", "category": "general", "country": "hk"},
    {"url": "https://www.hkheadline.com/", "source": "頭條日報", "category": "general", "country": "hk"},
]


# Additional feeds per country/lang for quota supplementation
SUPPLEMENTAL_FEEDS: Dict[str, List[Dict[str, str]]] = {
    "country:ca": [
        {"url": "https://www.cbc.ca/webfeed/rss/rss-topstories", "source": "CBC Canada", "category": "world", "country": "ca"},
        {"url": "https://globalnews.ca/feed/", "source": "Global News Canada", "category": "world", "country": "ca"},
    ],
    "country:gb": [
        {"url": "https://www.bbc.co.uk/news/uk/rss.xml", "source": "BBC UK", "category": "world", "country": "gb"},
    ],
    "country:au": [
        {"url": "https://www.abc.net.au/news/feed/51120/rss.xml", "source": "ABC Australia", "category": "world", "country": "au"},
    ],
    "country:nz": [
        {"url": "https://www.rnz.co.nz/rss", "source": "RNZ", "category": "world", "country": "nz"},
    ],
    "country:jp": [
        {"url": "https://www3.nhk.or.jp/nhkworld/en/news/rss/", "source": "NHK World", "category": "world", "country": "jp"},
        {"url": "https://asia.nikkei.com/rss/feed/nar", "source": "Nikkei Asia", "category": "world", "country": "jp"},
    ],
    "country:sg": [
        {"url": "https://www.straitstimes.com/news/world/rss.xml", "source": "Straits Times World", "category": "world", "country": "sg"},
    ],
    "country:hk": [
        {"url": "https://www.scmp.com/rss/2/feed", "source": "SCMP International", "category": "world", "country": "hk"},
        {"url": "https://www.hket.com/rss.xml", "source": "經濟日報", "category": "economy", "country": "hk"},
        {"url": "https://finance.now.com/news/rss/finance_rss.xml", "source": "Now 財經", "category": "finance", "country": "hk"},
    ],
}

# Supplemental by language (lang:<code>)
SUPPLEMENTAL_FEEDS_LANG: Dict[str, List[Dict[str, str]]] = {
    "lang:en": [
        {"url": "https://feeds.reuters.com/reuters/worldNews", "source": "Reuters World", "category": "world"},
        {"url": "https://www.theguardian.com/world/rss", "source": "The Guardian World", "category": "world"},
    ],
    "lang:zh": [
        {"url": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml", "source": "RTHK 即時本地", "category": "local", "country": "hk"},
        {"url": "https://news.mingpao.com/rss/ins/all.xml", "source": "明報 即時", "category": "local", "country": "hk"},
        {"url": "https://unwire.hk/feed/", "source": "Unwire.hk", "category": "technology", "country": "hk"},
        {"url": "https://www.hket.com/rss.xml", "source": "經濟日報", "category": "economy", "country": "hk"},
    ],
    "lang:ja": [
        {"url": "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "source": "Asahi Shimbun", "category": "world", "country": "jp"},
        {"url": "https://www3.nhk.or.jp/nhkworld/ja/news/rss/", "source": "NHK 日本語", "category": "world", "country": "jp"},
    ],
    "lang:fr": [
        {"url": "https://www.lemonde.fr/rss/une.xml", "source": "Le Monde", "category": "world", "country": "fr"},
    ],
    "lang:de": [
        {"url": "https://rss.dw.com/rdf/rss-de-all", "source": "DW (DE)", "category": "world", "country": "de"},
        {"url": "https://newsfeed.zeit.de/index", "source": "Die Zeit", "category": "world", "country": "de"},
    ],
    "lang:es": [
        {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "world", "country": "es"},
    ],
    "lang:it": [
        {"url": "https://www.ansa.it/sito/ansait_rss.xml", "source": "ANSA", "category": "world", "country": "it"},
    ],
}


def parse_feed(feed_conf: Dict[str, str]) -> List[Dict[str, str]]:
	# Build SSL context that uses system CA; as a fallback, allow unverified if needed
	context = None
	try:
		context = ssl.create_default_context()
	except Exception:
		context = None
	# fetch content resiliently then parse
	content = _fetch_content(feed_conf["url"]) or b""
	parsed = feedparser.parse(content) if content else feedparser.parse(b"")
	items: List[Dict[str, str]] = []
	for entry in (parsed.entries or []):
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
	if items:
		if getattr(parsed, "bozo", 0):
			print("Warning: bozo feed:", feed_conf.get("url"), getattr(parsed, "bozo_exception", None))
		return items
	# Try discovery on original URL first
	alt = _discover_feed_from_html(feed_conf["url"]) or None
	if alt:
		content2 = _fetch_content(alt)
		if content2:
			parsed2 = feedparser.parse(content2)
			for entry in (parsed2.entries or []):
				title = getattr(entry, "title", None) or ""
				link = getattr(entry, "link", None) or ""
				summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
				items.append({
					"title": title,
					"url": canonicalize_url(link) if link else link,
					"summary": summary,
					"source": feed_conf.get("source"),
					"category": feed_conf.get("category"),
					"published_at": None,
					"country": feed_conf.get("country"),
				})
			if items:
				return items
	# Try discovery on host-specific candidates
	try:
		host = urlparse(feed_conf["url"]).hostname or ""
	except Exception:
		host = ""
	if host and host in ALT_FEEDS:
		for cand in ALT_FEEDS[host]:
			alt2 = _discover_feed_from_html(cand)
			if not alt2:
				continue
			content3 = _fetch_content(alt2)
			if not content3:
				continue
			parsed3 = feedparser.parse(content3)
			for entry in (parsed3.entries or []):
				title = getattr(entry, "title", None) or ""
				link = getattr(entry, "link", None) or ""
				summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
				items.append({
					"title": title,
					"url": canonicalize_url(link) if link else link,
					"summary": summary,
					"source": feed_conf.get("source"),
					"category": feed_conf.get("category"),
					"published_at": None,
					"country": feed_conf.get("country"),
				})
			if items:
				return items
	# Fallback to simple HTML parsing
	html = _fetch_content(feed_conf["url"]) or b""
	if html:
		return _simple_html_to_items(html, feed_conf)
	print("HTTP error fetching feed", feed_conf.get("url"))
	FAILED.append({"url": feed_conf.get("url", ""), "reason": "no_entries"})
	return []


def ingest(items: List[Dict[str, str]]) -> None:
	if not items:
		return
	resp = requests.post(f"{BACKEND_URL}/articles/bulk", json={"items": items}, timeout=30)
	resp.raise_for_status()
	print("Ingested:", resp.json())


def _extend_feeds_from_file() -> List[Dict[str, str]]:
    extra: List[Dict[str, str]] = []
    path = os.getenv("FEEDS_FILE", os.path.join(os.path.dirname(__file__), "feeds_extra.json"))
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    extra.extend([x for x in data if isinstance(x, dict) and x.get("url")])
    except Exception as e:
        print("Failed to load FEEDS_FILE", path, e)
    envv = os.getenv("EXTRA_FEEDS")
    if envv:
        try:
            if envv.strip().startswith("["):
                data = json.loads(envv)
                if isinstance(data, list):
                    extra.extend([x for x in data if isinstance(x, dict) and x.get("url")])
            else:
                for token in envv.split(";"):
                    token = token.strip()
                    if not token:
                        continue
                    parts = token.split("|")
                    url = parts[0] if len(parts) > 0 else None
                    source = parts[1] if len(parts) > 1 else None
                    category = parts[2] if len(parts) > 2 else None
                    country = parts[3] if len(parts) > 3 else None
                    if url and source and category:
                        extra.append({"url": url, "source": source, "category": category, "country": country})
        except Exception as e:
            print("Failed to parse EXTRA_FEEDS", e)
    return extra


def main():
	all_items: List[Dict[str, str]] = []
	feeds = FEEDS[:]
	feeds.extend(_extend_feeds_from_file())
	for f in feeds:
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
	# write failures
	try:
		outp = os.path.join(os.path.dirname(__file__), "last_crawl_failures.json")
		with open(outp, "w", encoding="utf-8") as fh:
			json.dump(FAILED, fh, ensure_ascii=False, indent=2)
		print("Wrote failures:", outp, len(FAILED))
	except Exception as e:
		print("Error writing failures:", e)


if __name__ == "__main__":
	main()
