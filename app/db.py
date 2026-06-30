from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings


def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def session_scope() -> Iterator:
    engine = get_engine()
    with engine.begin() as connection:
        yield connection


def fetch_all(query: str, params: dict | None = None) -> list[dict]:
    engine = get_engine()
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params or {}).mappings()]
