from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped

from .db import Base


class Article(Base):
	__tablename__ = "articles"
	__table_args__ = (
		UniqueConstraint("url", name="uq_article_url"),
	)

	id: Mapped[int] = Column(Integer, primary_key=True)
	title: Mapped[str] = Column(String(512), nullable=False)
	url: Mapped[str] = Column(String(1024), nullable=False)
	summary: Mapped[Optional[str]] = Column(Text, nullable=True)
	source: Mapped[Optional[str]] = Column(String(128), nullable=True)
	category: Mapped[Optional[str]] = Column(String(64), nullable=True)
	published_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True, index=True)
	created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, nullable=False)

	interactions = relationship("UserInteraction", back_populates="article", cascade="all, delete-orphan")

	def to_dict(self):
		return {
			"id": self.id,
			"title": self.title,
			"url": self.url,
			"summary": self.summary,
			"source": self.source,
			"category": self.category,
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
