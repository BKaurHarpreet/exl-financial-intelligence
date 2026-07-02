from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings


def get_engine() -> Engine:
    settings = get_settings()
    if settings.database_url.startswith("sqlite:///"):
        import sqlite3
        from decimal import Decimal
        # Register Decimal adapter for sqlite3
        sqlite3.register_adapter(Decimal, lambda d: float(d) if not d.is_nan() else None)

        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return create_engine(settings.database_url, pool_pre_ping=True)



def initialize_database() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        for schema_file in sorted(Path("sql").glob("*.sql")):
            statements = [s.strip() for s in schema_file.read_text(encoding="utf-8").split(";") if s.strip()]
            for statement in statements:
                connection.execute(text(statement))


def session_scope() -> Iterator:
    engine = get_engine()
    with engine.begin() as connection:
        yield connection


def fetch_all(query: str, params: dict | None = None) -> list[dict]:
    engine = get_engine()
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params or {}).mappings()]
