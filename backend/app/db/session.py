import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

logger = logging.getLogger("db")

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _default_literal(column) -> str:
    default = column.default.arg if column.default is not None else None
    if isinstance(default, str):
        return f"'{default}'"
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, (int, float)):
        return str(default)
    return "NULL"


def _sync_missing_columns() -> None:
    """Additive-only migration: Base.metadata.create_all() only creates tables
    that don't exist yet, it silently skips ones that already do - so a model
    field added after the DB file already exists (e.g. Portfolio.exchange for
    multi-exchange support) would otherwise never actually reach the table.
    Adds any column present on the model but missing in the DB via a plain
    ALTER TABLE ADD COLUMN; never drops or modifies existing columns/data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in existing_tables:
                continue  # brand-new table - create_all() already handled it
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(engine.dialect)
                default_sql = f" DEFAULT {_default_literal(column)}" if column.default is not None else ""
                logger.info("Migrating: adding column %s.%s (%s)", table.name, column.name, col_type)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{default_sql}"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
