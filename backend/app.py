from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Base, get_engine, get_session
from .models import Article, User, UserInteraction
from .recommendation import recommend_for_user, get_default_preferences, update_preferences_from_feedback
try:
	from ml.infer import classify as ml_classify  # type: ignore
except Exception:  # pragma: no cover
	ml_classify = None  # type: ignore
def create_app() -> Flask:
	app = Flask(__name__, template_folder="templates")
	CORS(app)
	engine = get_engine()
	Base.metadata.create_all(bind=engine)
	@app.route("/health", methods=["GET"])  # simple health check
	def health():
		return jsonify({"status": "ok"})
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
					query = query.filter(Article.category == category)
				if source:
					query = query.filter(Article.source == source)
				if q:
					pattern = f"%{q}%"
					query = query.filter((Article.title.ilike(pattern)) | (Article.summary.ilike(pattern)))
				if order == "oldest":
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

	@app.route("/meta", methods=["GET"])  # distinct sources and categories for UI filters
	def meta():
		session = get_session()
		try:
			sources = sorted({s for (s,) in session.query(Article.source).filter(Article.source.isnot(None)).distinct().all()})
			categories = sorted({c for (c,) in session.query(Article.category).filter(Article.category.isnot(None)).distinct().all()})
			return jsonify({"sources": sources, "categories": categories})
		finally:
			session.close()
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
				article = session.execute(select(Article).where(Article.url == url)).scalars().first()
				if article:
					# Update minimal fields
					article.title = title
					article.summary = summary
					article.source = source
					article.published_at = published_at or article.published_at
					if not article.category:
						article.category = category
					updated += 1
				else:
					if category is None and ml_classify is not None:
						try:
							category = ml_classify(f"{title}\n{summary or ''}") or "general"
						except Exception:
							category = "general"
					article = Article(
						title=title,
						url=url,
						summary=summary,
						source=source,
						category=category or "general",
						published_at=published_at,
					)
					session.add(article)
					created += 1
			session.commit()
			return jsonify({"created": created, "updated": updated})
		finally:
			session.close()
	return app
if __name__ == "__main__":
	port = int(os.getenv("PORT", "5000"))
	app = create_app()
	app.run(host="0.0.0.0", port=port, debug=True)