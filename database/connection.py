# Database connection and shared model base.

import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from database.timeouts import connect_with_deadline


class DatabaseConfigurationError(ValueError):
    """Database settings need attention; messages never include secret values."""


def get_database_url() -> URL:
    # Read the repository-root .env only when database functionality is requested.
    settings = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    keys = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT")
    settings.update({key: os.environ[key] for key in keys if key in os.environ})
    missing = [key for key in keys[:3] if not settings.get(key) or not settings[key].strip()]
    if missing:
        raise DatabaseConfigurationError(
            "Database configuration is incomplete: " + ", ".join(missing) + ". "
            "Set these environment variables or copy .env.example to .env and fill in your values."
        )
    host = settings.get("POSTGRES_HOST", "127.0.0.1")
    if not host or not host.strip():
        raise DatabaseConfigurationError("POSTGRES_HOST must contain a database hostname.")
    try:
        port = int(settings.get("POSTGRES_PORT", "5432"))
    except (TypeError, ValueError):
        raise DatabaseConfigurationError(
            "POSTGRES_PORT must be an integer between 1 and 65535."
        ) from None
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("POSTGRES_PORT must be an integer between 1 and 65535.")
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings["POSTGRES_USER"],
        password=settings["POSTGRES_PASSWORD"],
        host=host,
        port=port,
        database=settings["POSTGRES_DB"],
    )


_engine = None
_engine_lock = Lock()


def get_engine():
    # Serialize first initialization so worker threads share one connection pool.
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = create_engine(
                get_database_url(),
                pool_pre_ping=True,
                pool_timeout=5,
                connect_args={
                    "connect_timeout": 3,
                    "options": "-c statement_timeout=10000 -c lock_timeout=3000 "
                               "-c idle_in_transaction_session_timeout=15000 "
                               "-c transaction_timeout=20000",
                },
            )
            event.listen(_engine, "do_connect", connect_with_deadline)
        return _engine


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine())


class _LazySessionFactory:
    # Preserve session/context-manager usage without validating settings on import.
    def __call__(self):
        return get_session_factory()()

    def begin(self):
        return get_session_factory().begin()


SessionLocal = _LazySessionFactory()


# All database model classes inherit from this base.
class Base(DeclarativeBase):
    pass
