import os
from pathlib import Path
from sqlalchemy import create_engine, text
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


def ensure_sqlite_column(table_name: str, column_name: str, column_ddl: str) -> None:
	"""Add a column if missing (SQLite only). column_ddl excludes the column name.
	Example: ensure_sqlite_column('articles', 'country', 'VARCHAR(32)')
	"""
	if not DATABASE_URL.startswith("sqlite"):
		return
	with _engine.connect() as conn:
		rows = conn.execute(text(f"PRAGMA table_info({table_name})"))
		existing = {r[1] for r in rows}
		if column_name not in existing:
			conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}"))
			conn.commit()

def ensure_sqlite_columns_for_articles():
	try:
		ensure_sqlite_column('articles', 'country', 'VARCHAR(32)')
		ensure_sqlite_column('articles', 'url_canonical', 'VARCHAR(1024)')
		ensure_sqlite_column('articles', 'url_hash', 'VARCHAR(64)')
		ensure_sqlite_column('articles', 'content', 'TEXT')
		ensure_sqlite_column('articles', 'source_norm', 'VARCHAR(128)')
		ensure_sqlite_column('articles', 'lang', 'VARCHAR(8)')
	except Exception:
		pass
