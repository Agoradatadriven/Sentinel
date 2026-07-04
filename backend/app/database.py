"""SQLAlchemy 2.0 engine, session factory, and declarative Base.

Works with SQLite (local, zero-setup) or PostgreSQL (prod) transparently via ``DATABASE_URL``.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # check_same_thread only matters for SQLite + threaded servers (uvicorn).
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create every table. Imports the models package so all tables are registered first."""
    from . import models  # noqa: F401  (registers all mappers on Base.metadata)

    Base.metadata.create_all(bind=engine)
