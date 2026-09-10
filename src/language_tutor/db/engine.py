"""Lazy database resources, closed by the application runtime."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from language_tutor import config


@lru_cache(maxsize=1)
def get_engine():
    if not config.DATABASE_URL:
        raise ValueError("缺少 DATABASE_URL，请检查环境配置")
    return create_engine(config.DATABASE_URL, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def SessionLocal() -> Session:
    """Return a new SQLAlchemy session; use as a context manager."""
    return get_session_factory()()


def close_database() -> None:
    """Dispose the engine and clear cached session factory / engine."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
