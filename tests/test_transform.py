"""Unit tests for the star-schema transform."""

import pandas as pd

from uk_property_pipeline.transform import (
    build_dim_date,
    build_dim_property,
    postcode_area,
    stable_key,
    transform,
)

LOOKUP = {"SW": "London", "M": "North West", "CF": "Wales", "B": "West Midlands"}


def test_stable_key_is_deterministic_and_52_bit():
    assert stable_key("a", "b") == stable_key("a", "b")
    assert stable_key("a", "b") != stable_key("b", "a")
    assert 0 <= stable_key("x") < 2**52


def test_postcode_area():
    s = pd.Series(["SW1A", "M20", "CF40", None], dtype="string")
    assert postcode_area(s).tolist()[:3] == ["SW", "M", "CF"]


def test_dim_date_financial_year():
    d = build_dim_date(pd.Timestamp("2024-03-15"), pd.Timestamp("2024-06-01"))
    assert len(d) == 366  # whole of 2024 (leap year)
    row = d.set_index("date")
    assert row.loc["2024-03-31", "uk_financial_year"] == "2023/24"
    assert row.loc["2024-04-01", "uk_financial_year"] == "2024/25"
    assert row.loc["2024-04-01", "uk_financial_quarter"] == 1
    assert row.loc["2024-01-01", "uk_financial_quarter"] == 4
    assert row.loc["2024-04-01", "date_key"] == 20240401
    assert d["date_key"].is_unique


def test_dim_property_keys_unique():
    p = build_dim_property()
    assert p["property_key"].is_unique
    assert {"Detached", "Flat/Maisonette"} <= set(p["property_type"])


def test_transform_star_schema(cleaned):
    df, _ = cleaned
    t = transform(df, LOOKUP)
    fact = t["fact_sales"]
    assert len(fact) == len(df) == 8
    assert fact["transaction_id"].is_unique
    for key, dim in [("date_key", "dim_date"), ("property_key", "dim_property"),
                     ("location_key", "dim_location")]:  # fmt: skip
        assert fact[key].isin(t[dim][key]).all()


def test_regions_assigned(cleaned):
    df, _ = cleaned
    loc = transform(df, LOOKUP)["dim_location"]
    assert loc.loc[loc["postcode"] == "SW1A 1AA", "region"].iloc[0] == "London"
    assert loc.loc[loc["postcode"] == "CF40 2PW", "region"].iloc[0] == "Wales"
    # invalid postcodes keep their town but get region Unknown
    bad = loc[loc["postcode"] == "UNKNOWN"]
    assert (bad["region"] == "Unknown").all()


def test_transform_is_deterministic(cleaned):
    df, _ = cleaned
    a = transform(df, LOOKUP)["fact_sales"]
    b = transform(df.sample(frac=1, random_state=1), LOOKUP)["fact_sales"]
    merged = a.merge(b, on="transaction_id", suffixes=("_a", "_b"))
    assert (merged["location_key_a"] == merged["location_key_b"]).all()
    assert (merged["property_key_a"] == merged["property_key_b"]).all()


def test_region_lookup_file_has_no_duplicates(cfg):
    lookup = pd.read_csv(cfg.region_lookup)
    assert lookup["postcode_area"].is_unique
    assert lookup["region"].notna().all()
