"""Integration tests for the load stage using an in-memory-style SQLite database."""

import pandas as pd
import pytest
from sqlalchemy import text

from uk_property_pipeline.load import get_engine, load
from uk_property_pipeline.transform import transform

LOOKUP = {"SW": "London", "M": "North West", "CF": "Wales", "B": "West Midlands"}


@pytest.fixture()
def engine(tmp_path):
    return get_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


def _count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


def test_load_creates_tables_and_rows(cleaned, engine):
    df, _ = cleaned
    load(transform(df, LOOKUP), engine)
    assert _count(engine, "fact_sales") == len(df)
    assert _count(engine, "dim_date") > 300
    assert _count(engine, "dim_location") > 0


def test_load_is_idempotent(cleaned, engine):
    df, _ = cleaned
    tables = transform(df, LOOKUP)
    load(tables, engine)
    first = {t: _count(engine, t) for t in tables}
    load(tables, engine)
    assert {t: _count(engine, t) for t in tables} == first


def test_changed_record_overwrites_existing(cleaned, engine):
    df, _ = cleaned
    tables = transform(df, LOOKUP)
    load(tables, engine)
    changed = {k: v.copy() for k, v in tables.items()}
    changed["fact_sales"] = changed["fact_sales"].iloc[:1].copy()
    changed["fact_sales"]["price"] = 999_999
    tid = changed["fact_sales"]["transaction_id"].iloc[0]
    load(changed, engine)
    assert _count(engine, "fact_sales") == len(df)
    with engine.connect() as conn:
        price = conn.execute(
            text("SELECT price FROM fact_sales WHERE transaction_id = :t"), {"t": tid}
        ).scalar_one()
    assert price == 999_999


def test_views_exist_and_exclude_outliers(cleaned, engine):
    df, _ = cleaned
    load(transform(df, LOOKUP), engine)
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT SUM(sales_count) FROM vw_price_by_property_type")
        ).scalar_one()
        regions = conn.execute(
            text("SELECT COUNT(*) FROM vw_monthly_avg_price_by_region")
        ).scalar_one()
    assert n == int((~df["is_outlier"]).sum())
    assert regions > 0


def test_yoy_growth_view(cleaned, engine):
    df, _ = cleaned
    base = df.iloc[[0]].copy()
    rows = []
    for year, price in ((2023, 200_000), (2024, 220_000)):
        r = pd.concat([base] * 120, ignore_index=True)
        r["transaction_id"] = [f"{year}-{i:04d}-{'X' * 26}"[:36] for i in range(120)]
        r["price"] = price
        r["is_outlier"] = False
        r["date_of_transfer"] = pd.Timestamp(f"{year}-06-01")
        rows.append(r)
    tables = transform(pd.concat(rows, ignore_index=True), LOOKUP)
    load(tables, engine)
    with engine.connect() as conn:
        res = conn.execute(
            text("SELECT year, yoy_growth_pct FROM vw_top_20_districts_by_growth")
        ).all()
    assert res == [(2024, 10.0)]
