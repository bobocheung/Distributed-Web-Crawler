import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _default_sqlite_url() -> str:
	project_root = Path(__file__).resolve().parents[1]
	data_dir = project_root / "data"
	data_dir.mkdir(parents=True, exist_ok=True)
	db_path = data_dir / "app.db"
	return f"sqlite:///{db_path}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_sqlite_url())

# check_same_thread is needed for SQLite with threads (Flask dev server)
_engine = create_engine(
	DATABASE_URL,
	echo=False,
	future=True,
	connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_engine():
	return _engine


def get_session():
	return SessionLocal()
