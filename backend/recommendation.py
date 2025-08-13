from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from .models import Article, User


def _parse_preferences(pref_str: str | None) -> Dict[str, float]:
	if not pref_str:
		return {}
	prefs: Dict[str, float] = {}
	# Format: "tech:1.5|business:0.7|sports:0.2"
	for token in pref_str.split("|"):
		if not token:
			continue
		if ":" in token:
			k, v = token.split(":", 1)
			try:
				prefs[k.strip()] = float(v)
			except ValueError:
				continue
	return prefs


def _serialize_preferences(prefs: Dict[str, float]) -> str:
	return "|".join(f"{k}:{v:.4f}" for k, v in prefs.items())


DEFAULT_CATEGORIES = [
	"general",
	"world",
	"business",
	"technology",
	"sports",
	"entertainment",
]


def get_default_preferences() -> Dict[str, float]:
	# Equal weights for all categories by default
	return {cat: 1.0 for cat in DEFAULT_CATEGORIES}


def update_preferences_from_feedback(pref_str: str | None, category: str | None, liked: bool) -> str:
	prefs = _parse_preferences(pref_str)
	if not prefs:
		prefs = get_default_preferences()
	if category is None:
		category = "general"
	delta = 0.2 if liked else -0.2
	new_weight = max(0.0, prefs.get(category, 1.0) + delta)
	prefs[category] = new_weight
	return _serialize_preferences(prefs)


def score_article_for_user(article: Article, user: User) -> float:
	prefs = _parse_preferences(user.preferences)
	if not prefs:
		prefs = get_default_preferences()
	category = article.category or "general"
	base = prefs.get(category, prefs.get("general", 1.0))

	# Recency boost: newer articles get higher scores
	if article.published_at:
		age_hours = max(0.0, (datetime.utcnow() - article.published_at).total_seconds() / 3600.0)
	else:
		age_hours = 1000.0
	recency_boost = max(0.1, 2.0 - age_hours / 24.0)

	return base * recency_boost


def recommend_for_user(session: Session, user: User, limit: int = 50) -> List[Article]:
	articles = session.query(Article).order_by(Article.published_at.desc().nullslast()).limit(1000).all()
	scored: List[Tuple[float, Article]] = []
	for a in articles:
		scored.append((score_article_for_user(a, user), a))
	scored.sort(key=lambda x: x[0], reverse=True)
	return [a for _, a in scored[:limit]]
