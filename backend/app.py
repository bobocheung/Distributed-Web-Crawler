from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from sqlalchemy import select, func, case
from sqlalchemy.exc import IntegrityError
from .db import Base, get_engine, get_session, ensure_sqlite_columns_for_articles
from .models import Article, User, UserInteraction, SavedArticle
from .recommendation import recommend_for_user, get_default_preferences, update_preferences_from_feedback, DEFAULT_COUNTRIES, DEFAULT_CATEGORIES, CATEGORY_DISPLAY
from .text_utils import canonicalize_url, url_hash as make_url_hash, normalize_source, detect_lang, infer_country_from_url
try:
	from ml.infer import classify as ml_classify  # type: ignore
except Exception:  # pragma: no cover
	ml_classify = None  # type: ignore
def create_app() -> Flask:
	app = Flask(__name__, template_folder="templates")
	CORS(app)
	engine = get_engine()
	if engine.dialect.name == "sqlite":
		Base.metadata.create_all(bind=engine)
		ensure_sqlite_columns_for_articles()
	@app.route("/health", methods=["GET"])  # simple health check
	def health():
		return jsonify({"status": "ok"})

	# quiet down favicon 404 in browser devtools
	@app.route("/favicon.ico")
	def favicon():
		return ("", 204)
	@app.route("/", methods=["GET"])  # minimal UI to verify setup quickly
	def index():
		return render_template("index.html")
	@app.route("/users", methods=["POST"])  # create user
	def create_user():
		payload = request.get_json(force=True) or {}
		email: str = (payload.get("email") or "").strip()
		preferences: Optional[Dict[str, float]] = payload.get("preferences")
		if not email:
			return jsonify({"error": "email is required"}), 400
		from .recommendation import _serialize_preferences
		if preferences:
			pref_str = _serialize_preferences(preferences)
		else:
			pref_str = _serialize_preferences(get_default_preferences())
		session = get_session()
		try:
			user = User(email=email, preferences=pref_str)
			session.add(user)
			session.commit()
			return jsonify({"id": user.id, "email": user.email}), 201
		except IntegrityError:
			session.rollback()
			existing = session.execute(select(User).where(User.email == email)).scalars().first()
			return jsonify({"id": existing.id, "email": existing.email}), 200
		finally:
			session.close()
	@app.route("/articles", methods=["GET"])  # list or personalized list with filters
	def list_articles():
		user_id = request.args.get("user_id", type=int)
		limit = request.args.get("limit", default=50, type=int)
		category = request.args.get("category")
		source = request.args.get("source")
		country = request.args.get("country")
		order = request.args.get("order", default="newest")  # newest|oldest
		q = request.args.get("q")
		page = request.args.get("page", default=1, type=int)
		page_size = request.args.get("page_size", default=30, type=int)
		session = get_session()
		try:
			if user_id:
				user = session.get(User, user_id)
				if not user:
					return jsonify({"error": "user not found"}), 404
				articles = recommend_for_user(session, user, limit=limit)
			else:
				query = session.query(Article)
				if category:
					# match either single category or multi-categories field
					query = query.filter(
						(Article.category == category) |
						(Article.categories.like(f"%,{category},%"))
					)
				if source:
					query = query.filter(Article.source == source)
				if country:
					query = query.filter(Article.country == country)
				lang = request.args.get("lang")
				if lang:
					query = query.filter(Article.lang == lang)
				if q:
					pattern = f"%{q}%"
					query = query.filter((Article.title.ilike(pattern)) | (Article.summary.ilike(pattern)))
				if order == "popular":
					# order by like counts (desc), then most recent
					likes_subq = (
						session.query(
							UserInteraction.article_id.label("a_id"),
							func.sum(case((UserInteraction.liked == True, 1), else_=0)).label("likes"),
						)
						.group_by(UserInteraction.article_id)
						.subquery()
					)
					query = (
						query.outerjoin(likes_subq, Article.id == likes_subq.c.a_id)
						.order_by(likes_subq.c.likes.desc().nullslast(), Article.published_at.desc().nullslast())
					)
				elif order == "oldest":
					query = query.order_by(Article.published_at.asc().nullslast())
				else:
					query = query.order_by(Article.published_at.desc().nullslast())
				# pagination
				offset = max(0, (page - 1) * page_size)
				limit_val = min(limit, page_size)
				articles = query.offset(offset).limit(limit_val).all()
			return jsonify([a.to_dict() for a in articles])
		finally:
			session.close()

	@app.route("/meta", methods=["GET"])  # distinct sources, categories, countries for UI filters
	def meta():
		session = get_session()
		try:
			sources = sorted({s for (s,) in session.query(Article.source).filter(Article.source.isnot(None)).distinct().all()})
			categories_db = sorted({c for (c,) in session.query(Article.category).filter(Article.category.isnot(None)).distinct().all()})
			countries_db = sorted({c for (c,) in session.query(Article.country).filter(Article.country.isnot(None)).distinct().all()})
			langs_db = sorted({l for (l,) in session.query(Article.lang).filter(Article.lang.isnot(None)).distinct().all()})
			# ensure we expose at least our defaults
			categories = sorted(set(categories_db).union(DEFAULT_CATEGORIES))
			countries = sorted(set(countries_db).union(DEFAULT_COUNTRIES))
			return jsonify({"sources": sources, "categories": categories, "countries": countries, "languages": langs_db, "category_display": CATEGORY_DISPLAY})
		finally:
			session.close()

	@app.route("/status", methods=["GET"])  # simple stats for UI
	def status():
		session = get_session()
		try:
			total = session.query(func.count(Article.id)).scalar() or 0
			last_pub = session.query(func.max(Article.published_at)).scalar()
			return jsonify({
				"total_articles": int(total),
				"last_published_at": last_pub.isoformat() if last_pub else None,
			})
		finally:
			session.close()

	@app.route("/stats", methods=["GET"])  # top sources/categories (7 days)
	def stats():
		session = get_session()
		try:
			# top sources
			source_rows = (
				session.query(Article.source, func.count(Article.id))
				.filter(Article.source.isnot(None))
				.group_by(Article.source)
				.order_by(func.count(Article.id).desc())
				.limit(10)
				.all()
			)
			cat_rows = (
				session.query(Article.category, func.count(Article.id))
				.filter(Article.category.isnot(None))
				.group_by(Article.category)
				.order_by(func.count(Article.id).desc())
				.limit(10)
				.all()
			)
			return jsonify({
				"top_sources": [{"source": s or "", "count": int(c)} for s, c in source_rows],
				"top_categories": [{"category": s or "", "count": int(c)} for s, c in cat_rows],
			})
		finally:
			session.close()

	@app.route("/stats_country_lang", methods=["GET"])  # counts per country and language
	def stats_country_lang():
		s = get_session()
		try:
			country_rows = (
				s.query(Article.country, func.count(Article.id), func.max(Article.published_at))
				.group_by(Article.country)
				.order_by(func.count(Article.id).desc())
				.all()
			)
			lang_rows = (
				s.query(Article.lang, func.count(Article.id))
				.group_by(Article.lang)
				.order_by(func.count(Article.id).desc())
				.all()
			)
			return jsonify({
				"countries": [
					{"code": c or "", "count": int(n or 0), "last_published_at": (lp.isoformat() if lp else None)}
					for c, n, lp in country_rows
				],
				"languages": [
					{"code": l or "", "count": int(n or 0)}
					for l, n in lang_rows
				],
			})
		finally:
			s.close()

	@app.route("/sources_country_map", methods=["GET"])
	def sources_country_map():
		s = get_session()
		try:
			rows = (
				s.query(Article.source_norm, Article.source, Article.country, func.count(Article.id))
				.group_by(Article.source_norm, Article.source, Article.country)
				.all()
			)
			acc: Dict[str, Dict[str, Any]] = {}
			for sn, sname, c, n in rows:
				key = (sn or sname or "").strip() or "unknown"
				item = acc.setdefault(key, {"source": key, "best_country": None, "counts": {}})
				item["counts"][c or ""] = int(n)
			# pick majority country
			for k, v in acc.items():
				best = sorted(v["counts"].items(), key=lambda x: x[1], reverse=True)
				v["best_country"] = best[0][0] if best else ""
			return jsonify(list(acc.values()))
		finally:
			s.close()

	@app.route("/language_accuracy", methods=["GET"])
	def language_accuracy():
		s = get_session()
		try:
			total = s.query(func.count(Article.id)).scalar() or 0
			per = s.query(Article.lang, func.count(Article.id)).group_by(Article.lang).all()
			return jsonify({
				"total": int(total),
				"by_lang": [{"lang": l or "", "count": int(n)} for l, n in per],
			})
		finally:
			s.close()

	@app.route("/crawl_stats", methods=["GET"])  # recent counts (24h/48h) by source/country/lang
	def crawl_stats():
		from datetime import datetime, timedelta
		s = get_session()
		try:
			now = datetime.utcnow()
			cut24 = now - timedelta(hours=24)
			cut48 = now - timedelta(hours=48)
			def agg(cut):
				src = (
					s.query(Article.source, func.count(Article.id))
					.filter(Article.created_at >= cut)
					.group_by(Article.source)
					.all()
				)
				cty = (
					s.query(Article.country, func.count(Article.id))
					.filter(Article.created_at >= cut)
					.group_by(Article.country)
					.all()
				)
				lng = (
					s.query(Article.lang, func.count(Article.id))
					.filter(Article.created_at >= cut)
					.group_by(Article.lang)
					.all()
				)
				return {
					"by_source": [{"source": s or "", "count": int(n)} for s, n in src],
					"by_country": [{"country": c or "", "count": int(n)} for c, n in cty],
					"by_lang": [{"lang": l or "", "count": int(n)} for l, n in lng],
				}
			return jsonify({"last24h": agg(cut24), "last48h": agg(cut48)})
		finally:
			s.close()

	@app.route("/admin/fix_countries", methods=["POST"])  # one-off: fill missing countries by URL inference
	def admin_fix_countries():
		s = get_session()
		try:
			rows = s.query(Article).filter((Article.country.is_(None)) | (Article.country == "")).all()
			fixed = 0
			for a in rows:
				inf = infer_country_from_url(a.url)
				if inf:
					a.country = inf
					fixed += 1
			s.commit()
			return jsonify({"fixed": fixed})
		finally:
			s.close()

	@app.route("/crawl", methods=["POST"])  # trigger a crawl cycle via Celery
	def trigger_crawl():
		try:
			from tasks.schedule import schedule_feeds  # lazy import to avoid overhead
			schedule_feeds.delay()
			return jsonify({"enqueued": True})
		except Exception as e:
			return jsonify({"enqueued": False, "error": str(e)}), 500
	@app.route("/feedback", methods=["POST"])  # record like/dislike and update prefs
	def feedback():
		payload = request.get_json(force=True) or {}
		user_id = payload.get("user_id")
		article_id = payload.get("article_id")
		liked = bool(payload.get("liked", True))
		if not user_id or not article_id:
			return jsonify({"error": "user_id and article_id are required"}), 400
		session = get_session()
		try:
			user = session.get(User, int(user_id))
			article = session.get(Article, int(article_id))
			if not user or not article:
				return jsonify({"error": "user or article not found"}), 404
			# upsert interaction
			existing = (
				session.query(UserInteraction)
				.filter(UserInteraction.user_id == user.id, UserInteraction.article_id == article.id)
				.one_or_none()
			)
			if existing:
				existing.liked = liked
			else:
				session.add(UserInteraction(user_id=user.id, article_id=article.id, liked=liked))
			# update preferences
			user.preferences = update_preferences_from_feedback(user.preferences, article.category, liked)
			session.commit()
			return jsonify({"status": "ok"})
		finally:
			session.close()

	@app.route("/articles/<int:article_id>", methods=["GET"])  # article detail
	def article_detail(article_id: int):
		s = get_session()
		try:
			obj = s.get(Article, article_id)
			if not obj:
				return jsonify({"error": "not found"}), 404
			return jsonify(obj.to_dict())
		finally:
			s.close()
	@app.route("/articles/bulk", methods=["POST"])  # ingest articles from crawler
	def bulk_articles():
		payload = request.get_json(force=True) or {}
		items: List[Dict[str, Any]] = payload.get("items") or []
		if not isinstance(items, list) or not items:
			return jsonify({"error": "items must be a non-empty list"}), 400
		session = get_session()
		created = 0
		updated = 0
		try:
			for it in items:
				url = (it.get("url") or "").strip()
				title = (it.get("title") or "").strip()
				if not url or not title:
					continue
				summary = (it.get("summary") or "").strip() or None
				source = (it.get("source") or "").strip() or None
				category = (it.get("category") or "").strip() or None
				published_at_raw = it.get("published_at")
				published_at = None
				if published_at_raw:
					try:
						published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)
					except Exception:
						published_at = None
				# extended fields + multi-categories
				url_canonical = canonicalize_url(url) if url else url
				url_hash_val = make_url_hash(url_canonical) if url_canonical else None
				source_norm = normalize_source(source)
				lang = (it.get("lang") or "").strip() or (detect_lang(summary) if summary else None)
				# derive multi categories by simple rules
				cats = []
				text_for_clf = f"{title}\n{summary or ''}".lower()
				def add_cat(key):
					if key and key not in cats:
						cats.append(key)
				# rules
				if any(k in text_for_clf for k in [" ai ","人工智能","機器學習","半導體","晶片","chip","software","app","科技","tech"]):
					add_cat("technology")
				if any(k in text_for_clf for k in ["經濟","inflation","cpi","gdp","經濟成長","economic"]):
					add_cat("economy")
				if any(k in text_for_clf for k in ["finance","bank","利率","hibor","股市","market","證券"]):
					add_cat("finance"); add_cat("economy")
				if any(k in text_for_clf for k in ["policy","regulation","監管","立法","政府","部長","部會"]):
					add_cat("politics")
				if any(k in text_for_clf for k in ["health","covid","醫療","醫院","健康"]):
					add_cat("health")
				if any(k in text_for_clf for k in ["sport","比賽","球隊","球員","world cup","奧運"]):
					add_cat("sports")
				if any(k in text_for_clf for k in ["entertainment","電影","影視","音樂","明星"]):
					add_cat("entertainment")
				if any(k in text_for_clf for k in ["climate","環境","污染","綠色","減碳"]):
					add_cat("environment")
				# fallbacks
				if not cats:
					cats = [category or "general"]
				categories_str = "," + ",".join(sorted(set(cats))) + ","

				article = session.execute(select(Article).where(Article.url == url)).scalars().first()
				if article:
					# Update minimal fields
					article.title = title
					article.summary = summary
					article.source = source
					article.published_at = published_at or article.published_at
					if not article.category:
						article.category = category
					# update multi-categories
					text_for_clf_upd = f"{title}\n{summary or ''}".lower()
					cats_upd = []
					def add_cat_upd(k):
						if k and k not in cats_upd:
							cats_upd.append(k)
					if any(k in text_for_clf_upd for k in [" ai ","人工智能","機器學習","半導體","晶片","chip","software","app","科技","tech"]):
						add_cat_upd("technology")
					if any(k in text_for_clf_upd for k in ["經濟","inflation","cpi","gdp","經濟成長","economic"]):
						add_cat_upd("economy")
					if any(k in text_for_clf_upd for k in ["finance","bank","利率","hibor","股市","market","證券"]):
						add_cat_upd("finance")
					if any(k in text_for_clf_upd for k in ["policy","regulation","監管","立法","政府","部長","部會"]):
						add_cat_upd("politics")
					if any(k in text_for_clf_upd for k in ["health","covid","醫療","醫院","健康"]):
						add_cat_upd("health")
					if any(k in text_for_clf_upd for k in ["sport","比賽","球隊","球員","world cup","奧運"]):
						add_cat_upd("sports")
					if any(k in text_for_clf_upd for k in ["entertainment","電影","影視","音樂","明星"]):
						add_cat_upd("entertainment")
					if any(k in text_for_clf_upd for k in ["climate","環境","污染","綠色","減碳"]):
						add_cat_upd("environment")
					if cats_upd:
						article.categories = "," + ",".join(sorted(set(cats_upd))) + ","
					# prefer incoming, fallback to URL inference, then keep existing
					incoming_country2 = (it.get("country") or None)
					inferred_country2 = infer_country_from_url(url)
					article.country = incoming_country2 or inferred_country2 or article.country
					article.url_canonical = url_canonical or article.url_canonical
					article.url_hash = url_hash_val or article.url_hash
					article.source_norm = source_norm or article.source_norm
					article.lang = lang or article.lang
					updated += 1
				else:
					# Determine final category
					final_category = category
					if final_category is None:
						if ml_classify is not None:
							try:
								final_category = ml_classify(f"{title}\n{summary or ''}") or "general"
							except Exception:
								final_category = "general"
						else:
							final_category = "general"
					new_article = Article(
						title=title,
						url=url,
						summary=summary,
						source=source,
						category=final_category or "general",
						categories=categories_str,
						country=(it.get("country") or infer_country_from_url(url)),
						published_at=published_at,
						url_canonical=url_canonical,
						url_hash=url_hash_val,
						source_norm=source_norm,
						lang=lang,
					)
					session.add(new_article)
					created += 1
			session.commit()
			return jsonify({"created": created, "updated": updated})
		finally:
			session.close()

	@app.route("/saves", methods=["GET"])  # list saved
	def list_saves():
		user_id = request.args.get("user_id", type=int)
		if not user_id:
			return jsonify([])
		s = get_session()
		try:
			rows = (
				s.query(Article)
				.join(SavedArticle, SavedArticle.article_id == Article.id)
				.filter(SavedArticle.user_id == user_id)
				.order_by(Article.published_at.desc().nullslast())
				.limit(200)
				.all()
			)
			return jsonify([a.to_dict() for a in rows])
		finally:
			s.close()

	@app.route("/saves", methods=["POST"])  # toggle save
	def toggle_save():
		payload = request.get_json(force=True) or {}
		user_id = payload.get("user_id")
		article_id = payload.get("article_id")
		action = (payload.get("action") or "toggle").lower()
		if not user_id or not article_id:
			return jsonify({"error": "user_id and article_id required"}), 400
		s = get_session()
		try:
			ex = (
				s.query(SavedArticle)
				.filter(SavedArticle.user_id == int(user_id), SavedArticle.article_id == int(article_id))
				.one_or_none()
			)
			if ex and action in ("toggle", "remove"):
				s.delete(ex)
				s.commit()
				return jsonify({"saved": False})
			if not ex and action in ("toggle", "add"):
				s.add(SavedArticle(user_id=int(user_id), article_id=int(article_id)))
				s.commit()
				return jsonify({"saved": True})
			return jsonify({"saved": bool(ex)})
		finally:
			s.close()

	@app.route("/trending", methods=["GET"])  # last 48h by likes
	def trending():
		s = get_session()
		try:
			from datetime import datetime, timedelta
			cut = datetime.utcnow() - timedelta(hours=48)
			likes_subq = (
				s.query(
					UserInteraction.article_id.label("a_id"),
					func.sum(case((UserInteraction.liked == True, 1), else_=0)).label("likes"),
				)
				.filter(UserInteraction.created_at >= cut)
				.group_by(UserInteraction.article_id)
				.subquery()
			)
			rows = (
				s.query(Article)
				.outerjoin(likes_subq, Article.id == likes_subq.c.a_id)
				.order_by(likes_subq.c.likes.desc().nullslast(), Article.published_at.desc().nullslast())
				.limit(50)
				.all()
			)
			return jsonify([a.to_dict() for a in rows])
		finally:
			s.close()
	return app
if __name__ == "__main__":
	port = int(os.getenv("PORT", "5000"))
	app = create_app()
	app.run(host="0.0.0.0", port=port, debug=True)