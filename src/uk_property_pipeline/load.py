"""Stage 5: create the schema and load the star schema idempotently.

Strategy (portable across PostgreSQL, SQLite and SQL Server):

* Dimensions use hash-based surrogate keys, so a re-run produces identical keys.
  Only rows whose key is not already present are inserted.
* ``fact_sales`` is loaded through a staging table. Existing rows with the same
  ``transaction_id`` are deleted and re-inserted, which makes re-runs
  idempotent and lets Land Registry "change" records overwrite earlier versions.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    text,
)

from .config import PROJECT_ROOT, get_database_url

logger = logging.getLogger(__name__)

VIEWS_SQL = PROJECT_ROOT / "sql" / "views.sql"
CHUNK_ROWS = 20_000

metadata = MetaData()

dim_date = Table(
    "dim_date",
    metadata,
    Column("date_key", Integer, primary_key=True, autoincrement=False),
    Column("date", Date, nullable=False, unique=True),
    Column("year", SmallInteger, nullable=False),
    Column("quarter", SmallInteger, nullable=False),
    Column("month", SmallInteger, nullable=False),
    Column("month_name", String(10), nullable=False),
    Column("year_month", String(7), nullable=False),
    Column("day_of_month", SmallInteger, nullable=False),
    Column("day_name", String(10), nullable=False),
    Column("uk_financial_year", String(7), nullable=False),
    Column("uk_financial_quarter", SmallInteger, nullable=False),
    Index("ix_dim_date_year_month", "year_month"),
)

dim_property = Table(
    "dim_property",
    metadata,
    Column("property_key", BigInteger, primary_key=True, autoincrement=False),
    Column("property_type", String(20), nullable=False),
    Column("build_status", String(20), nullable=False),
    Column("is_new_build", Boolean, nullable=False),
    Column("tenure", String(20), nullable=False),
    UniqueConstraint("property_type", "build_status", "tenure"),
)

dim_location = Table(
    "dim_location",
    metadata,
    Column("location_key", BigInteger, primary_key=True, autoincrement=False),
    Column("postcode", String(10), nullable=False),
    Column("postcode_district", String(5), nullable=False),
    Column("town_city", String(100), nullable=False),
    Column("district", String(100), nullable=False),
    Column("county", String(100), nullable=False),
    Column("region", String(40), nullable=False),
    UniqueConstraint("postcode", "town_city", "district", "county"),
    Index("ix_dim_location_region", "region"),
    Index("ix_dim_location_district", "district"),
)

fact_sales = Table(
    "fact_sales",
    metadata,
    Column("transaction_id", String(36), primary_key=True),
    Column("price", BigInteger, CheckConstraint("price > 0"), nullable=False),
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("property_key", BigInteger, ForeignKey("dim_property.property_key"), nullable=False),
    Column("location_key", BigInteger, ForeignKey("dim_location.location_key"), nullable=False),
    Column("ppd_category_type", String(1)),
    Column("record_status", String(1), nullable=False),
    Column("is_valid_postcode", Boolean, nullable=False),
    Column("is_low_price", Boolean, nullable=False),
    Column("is_iqr_outlier", Boolean, nullable=False),
    Column("is_outlier", Boolean, nullable=False),
    Index("ix_fact_sales_date_key", "date_key"),
    Index("ix_fact_sales_property_key", "property_key"),
    Index("ix_fact_sales_location_key", "location_key"),
    Index("ix_fact_sales_is_outlier", "is_outlier"),
)

DIMENSIONS = {
    "dim_date": "date_key",
    "dim_property": "property_key",
    "dim_location": "location_key",
}


def get_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine from ``url`` or the DATABASE_URL setting."""
    url = url or get_database_url()
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url)


def create_schema(engine: Engine) -> None:
    """Create all tables, keys and indexes if they do not exist."""
    metadata.create_all(engine)
    logger.info("Schema ready on %s", engine.dialect.name)


def _insert_missing(engine: Engine, name: str, key: str, df: pd.DataFrame) -> int:
    """Insert dimension rows whose key is not already in the table."""
    staging = f"stg_{name}"
    df.to_sql(staging, engine, if_exists="replace", index=False, chunksize=CHUNK_ROWS)
    cols = ", ".join(f'"{c}"' for c in df.columns)
    stg_cols = ", ".join(f's."{c}"' for c in df.columns)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"INSERT INTO {name} ({cols}) SELECT {stg_cols} FROM {staging} s "
                f'WHERE NOT EXISTS (SELECT 1 FROM {name} t WHERE t."{key}" = s."{key}")'
            )
        )
        conn.execute(text(f"DROP TABLE {staging}"))
    inserted = result.rowcount or 0
    logger.info("%s: %d new row(s) of %d", name, inserted, len(df))
    return inserted


def _upsert_fact(engine: Engine, df: pd.DataFrame) -> int:
    """Replace fact rows for the incoming transaction ids via a staging table."""
    df = df.copy()
    for col in ("is_valid_postcode", "is_low_price", "is_iqr_outlier", "is_outlier"):
        df[col] = df[col].astype(bool)
    df.to_sql("stg_fact_sales", engine, if_exists="replace", index=False, chunksize=CHUNK_ROWS)
    cols = ", ".join(df.columns)
    stg_cols = ", ".join(f"s.{c}" for c in df.columns)
    with engine.begin() as conn:
        deleted = conn.execute(
            text(
                "DELETE FROM fact_sales WHERE transaction_id IN "
                "(SELECT transaction_id FROM stg_fact_sales)"
            )
        ).rowcount
        conn.execute(
            text(f"INSERT INTO fact_sales ({cols}) SELECT {stg_cols} FROM stg_fact_sales s")
        )
        conn.execute(text("DROP TABLE stg_fact_sales"))
    logger.info("fact_sales: %d row(s) loaded (%d replaced existing)", len(df), deleted or 0)
    return len(df)


def create_views(engine: Engine, views_file: Path = VIEWS_SQL) -> int:
    """(Re)create reporting views from sql/views.sql."""
    statements = [s.strip() for s in views_file.read_text(encoding="utf-8").split(";")]
    statements = [
        s for s in statements if s and not all(line.startswith("--") for line in s.splitlines())
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    logger.info("Created/updated %d view statement(s)", len(statements))
    return len(statements)


def load(tables: dict[str, pd.DataFrame], engine: Engine | None = None) -> dict[str, int]:
    """Load all star-schema tables idempotently and refresh the views."""
    engine = engine or get_engine()
    create_schema(engine)
    counts = {
        name: _insert_missing(engine, name, key, tables[name]) for name, key in DIMENSIONS.items()
    }
    counts["fact_sales"] = _upsert_fact(engine, tables["fact_sales"])
    create_views(engine)
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM fact_sales")).scalar_one()
    logger.info("fact_sales now holds %d row(s)", total)
    return counts
