from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped

from .db import Base


class Article(Base):
	__tablename__ = "articles"
	__table_args__ = (
		UniqueConstraint("url", name="uq_article_url"),
		UniqueConstraint("url_hash", name="uq_article_url_hash"),
	)

	id: Mapped[int] = Column(Integer, primary_key=True)
	title: Mapped[str] = Column(String(512), nullable=False)
	url: Mapped[str] = Column(String(1024), nullable=False)
	url_canonical: Mapped[Optional[str]] = Column(String(1024), nullable=True, index=True)
	url_hash: Mapped[Optional[str]] = Column(String(64), nullable=True, index=True)
	summary: Mapped[Optional[str]] = Column(Text, nullable=True)
	content: Mapped[Optional[str]] = Column(Text, nullable=True)
	source: Mapped[Optional[str]] = Column(String(128), nullable=True)
	source_norm: Mapped[Optional[str]] = Column(String(128), nullable=True, index=True)
	category: Mapped[Optional[str]] = Column(String(64), nullable=True)
	country: Mapped[Optional[str]] = Column(String(32), nullable=True, index=True)
	published_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True, index=True)
	lang: Mapped[Optional[str]] = Column(String(8), nullable=True, index=True)
	content_simhash: Mapped[Optional[str]] = Column(String(32), nullable=True, index=True)
	created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

	interactions = relationship("UserInteraction", back_populates="article", cascade="all, delete-orphan")

	def to_dict(self):
		return {
			"id": self.id,
			"title": self.title,
			"url": self.url,
			"summary": self.summary,
			"content": (self.content[:500] + "...") if self.content and len(self.content) > 500 else self.content,
			"source": self.source,
			"source_norm": self.source_norm,
			"category": self.category,
			"country": self.country,
			"lang": self.lang,
			"published_at": self.published_at.isoformat() if self.published_at else None,
		}


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = Column(Integer, primary_key=True)
	email: Mapped[str] = Column(String(256), unique=True, nullable=False, index=True)
	# Simple JSON-as-string for preferences: "category:weight,category:weight" or a pipe-delimited string
	# Keeps dependencies light without a JSON column; parsing handled in app logic
	preferences: Mapped[Optional[str]] = Column(Text, nullable=True)
	created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

	interactions = relationship("UserInteraction", back_populates="user", cascade="all, delete-orphan")


class UserInteraction(Base):
	__tablename__ = "user_interactions"
	__table_args__ = (
		UniqueConstraint("user_id", "article_id", name="uq_user_article"),
	)

	id: Mapped[int] = Column(Integer, primary_key=True)
	user_id: Mapped[int] = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
	article_id: Mapped[int] = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
	liked: Mapped[bool] = Column(Boolean, nullable=False)
	created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

	user = relationship("User", back_populates="interactions")
	article = relationship("Article", back_populates="interactions")
