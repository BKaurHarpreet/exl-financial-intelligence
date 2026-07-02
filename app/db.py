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



# Columns added after a table already existed in deployed databases.
# CREATE TABLE IF NOT EXISTS is a no-op against an existing table, so any
# column added to the .sql schema files after first deploy needs an explicit
# ALTER TABLE here, or existing databases silently keep the old shape and
# every query referencing the new column throws "no such column".
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("gold_kpi_trends", "source_address", "TEXT"),
    ("gold_segment_trends", "sheet_name", "TEXT"),
    ("gold_segment_trends", "source_address", "TEXT"),
    ("gold_geography_trends", "sheet_name", "TEXT"),
    ("gold_geography_trends", "source_address", "TEXT"),
    ("gold_cash_flow_trends", "source_address", "TEXT"),
    ("gold_cash_position", "source_address", "TEXT"),
]


def _run_column_migrations(connection) -> None:
    for table, column, col_type in _COLUMN_MIGRATIONS:
        existing = connection.execute(text(f"PRAGMA table_info({table})")).mappings().all()
        if not existing:
            continue  # table doesn't exist yet -- CREATE TABLE above will include the column
        existing_names = {row["name"] for row in existing}
        if column not in existing_names:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def initialize_database() -> None:
    engine = get_engine()
    with engine.begin() as connection:
        for schema_file in sorted(Path("sql").glob("*.sql")):
            statements = [s.strip() for s in schema_file.read_text(encoding="utf-8").split(";") if s.strip()]
            for statement in statements:
                connection.execute(text(statement))
        _run_column_migrations(connection)


def session_scope() -> Iterator:
    engine = get_engine()
    with engine.begin() as connection:
        yield connection


def fetch_all(query: str, params: dict | None = None) -> list[dict]:
    engine = get_engine()
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params or {}).mappings()]
