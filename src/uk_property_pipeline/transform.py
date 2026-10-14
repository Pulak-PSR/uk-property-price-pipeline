"""Stage 4: build the star schema (fact_sales + three dimensions)."""

from __future__ import annotations

import hashlib
import itertools
import logging
from pathlib import Path

import pandas as pd

from .clean import DURATION_MAP, OLD_NEW_MAP, PROPERTY_TYPE_MAP

logger = logging.getLogger(__name__)

UNKNOWN = "UNKNOWN"
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def stable_key(*parts: object) -> int:
    """Deterministic 52-bit surrogate key from natural-key parts.

    Hash-based keys stay stable across runs, so incremental loads never need
    a lookup against the database. 52 bits keeps the value exactly
    representable in Power BI (double) while making collisions negligible.
    """
    digest = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 12


def postcode_area(postcode_district: pd.Series) -> pd.Series:
    """Leading letters of the outward code, e.g. ``SW1A`` -> ``SW``."""
    return postcode_district.astype("string").str.extract(r"^([A-Z]+)", expand=False)


def load_region_lookup(path: Path) -> dict[str, str]:
    """Read the postcode-area -> region lookup CSV."""
    lookup = pd.read_csv(path, dtype=str)
    return dict(zip(lookup["postcode_area"], lookup["region"], strict=True))


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Calendar dimension covering whole years from ``start`` to ``end``.

    Includes the UK financial year (April to March), labelled e.g. ``2024/25``.
    """
    days = pd.date_range(f"{start.year}-01-01", f"{end.year}-12-31", freq="D")
    d = pd.DataFrame({"date": days})
    d["date_key"] = d["date"].dt.strftime("%Y%m%d").astype(int)
    d["year"] = d["date"].dt.year
    d["quarter"] = d["date"].dt.quarter
    d["month"] = d["date"].dt.month
    d["month_name"] = d["month"].map(lambda m: MONTH_NAMES[m - 1])
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["day_of_month"] = d["date"].dt.day
    d["day_name"] = d["date"].dt.dayofweek.map(lambda i: DAY_NAMES[i])
    fy_start = d["year"].where(d["month"] >= 4, d["year"] - 1)
    d["uk_financial_year"] = (
        fy_start.astype(str) + "/" + ((fy_start + 1) % 100).astype(str).str.zfill(2)
    )
    d["uk_financial_quarter"] = ((d["month"] - 4) % 12 // 3 + 1).astype(int)
    return d[
        ["date_key", "date", "year", "quarter", "month", "month_name", "year_month",
         "day_of_month", "day_name", "uk_financial_year", "uk_financial_quarter"]
    ]  # fmt: skip


def build_dim_property() -> pd.DataFrame:
    """Static property dimension: every type x new-build x tenure combination.

    Built from the code maps rather than the data so keys never shift between runs.
    """
    types = [*PROPERTY_TYPE_MAP.values(), "Unknown"]
    olds = [*OLD_NEW_MAP.values(), "Unknown"]
    tenures = [*DURATION_MAP.values(), "Unknown"]
    rows = [
        {
            "property_key": stable_key(t, o, d),
            "property_type": t,
            "build_status": o,
            "is_new_build": o == "New Build",
            "tenure": d,
        }
        for t, o, d in itertools.product(types, olds, tenures)
    ]
    return pd.DataFrame(rows)


def _add_region(df: pd.DataFrame, lookup: dict[str, str]) -> pd.Series:
    area = postcode_area(df["postcode_district"])
    return area.map(lookup).fillna("Unknown").astype(str)


def build_dim_location(df: pd.DataFrame, lookup: dict[str, str]) -> pd.DataFrame:
    """Location dimension at grain (postcode, town, district, county)."""
    loc = df[["postcode", "postcode_district", "town_city", "district", "county"]].copy()
    loc["postcode"] = loc["postcode"].where(df["is_valid_postcode"]).fillna(UNKNOWN).astype(str)
    loc["postcode_district"] = loc["postcode_district"].fillna(UNKNOWN).astype(str)
    for col in ("town_city", "district", "county"):
        loc[col] = loc[col].astype(str)
    loc["region"] = _add_region(df, lookup)
    loc = loc.drop_duplicates().reset_index(drop=True)
    loc.insert(
        0,
        "location_key",
        [
            stable_key(p, t, d, c)
            for p, t, d, c in zip(
                loc["postcode"], loc["town_city"], loc["district"], loc["county"], strict=True
            )
        ],
    )
    if loc["location_key"].duplicated().any():
        raise RuntimeError("Hash collision in dim_location surrogate keys")
    return loc


def transform(df: pd.DataFrame, region_lookup: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Turn the cleaned frame into star-schema tables.

    Returns a dict with ``dim_date``, ``dim_property``, ``dim_location`` and ``fact_sales``.
    """
    dim_date = build_dim_date(df["date_of_transfer"].min(), df["date_of_transfer"].max())
    dim_property = build_dim_property()
    dim_location = build_dim_location(df, region_lookup)

    postcode = df["postcode"].where(df["is_valid_postcode"]).fillna(UNKNOWN).astype(str)
    fact = pd.DataFrame(
        {
            "transaction_id": df["transaction_id"].astype(str),
            "price": df["price"].astype("int64"),
            "date_key": df["date_of_transfer"].dt.strftime("%Y%m%d").astype(int),
            "property_key": [
                stable_key(t, o, d)
                for t, o, d in zip(
                    df["property_type_label"],
                    df["old_new_label"],
                    df["duration_label"],
                    strict=True,
                )
            ],
            "location_key": [
                stable_key(p, t, d, c)
                for p, t, d, c in zip(
                    postcode, df["town_city"], df["district"], df["county"], strict=True
                )
            ],
            "ppd_category_type": df["ppd_category_type"].astype("object"),
            "record_status": df["record_status"].astype(str),
            "is_valid_postcode": df["is_valid_postcode"].astype(bool),
            "is_low_price": df["is_low_price"].astype(bool),
            "is_iqr_outlier": df["is_iqr_outlier"].astype(bool),
            "is_outlier": df["is_outlier"].astype(bool),
        }
    )
    fact["ppd_category_type"] = fact["ppd_category_type"].where(
        fact["ppd_category_type"].notna(), None
    )

    # referential integrity: every fact key must exist in its dimension
    for key, dim in (("property_key", dim_property), ("location_key", dim_location),
                     ("date_key", dim_date)):  # fmt: skip
        missing = ~fact[key].isin(dim[key])
        if missing.any():
            raise RuntimeError(
                f"{int(missing.sum())} fact rows have no matching {key} in dimension"
            )

    logger.info(
        "Star schema: fact_sales=%d, dim_date=%d, dim_property=%d, dim_location=%d",
        len(fact), len(dim_date), len(dim_property), len(dim_location),
    )  # fmt: skip
    return {
        "dim_date": dim_date,
        "dim_property": dim_property,
        "dim_location": dim_location,
        "fact_sales": fact,
    }
