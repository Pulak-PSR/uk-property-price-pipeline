"""Stage 2: clean raw Price Paid Data and write a data-quality report."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

logger = logging.getLogger(__name__)

PROPERTY_TYPE_MAP = {
    "D": "Detached",
    "S": "Semi-Detached",
    "T": "Terraced",
    "F": "Flat/Maisonette",
    "O": "Other",
}
OLD_NEW_MAP = {"Y": "New Build", "N": "Existing"}
DURATION_MAP = {"F": "Freehold", "L": "Leasehold"}
TEXT_COLUMNS = ["paon", "saon", "street", "locality", "town_city", "district", "county"]
CODE_COLUMNS = ["property_type", "old_new", "duration", "ppd_category_type", "record_status"]
REQUIRED_COLUMNS = ["transaction_id", "price", "date_of_transfer"]

# Standard UK postcode pattern, applied to the normalised "OUT IN" form.
POSTCODE_RE = re.compile(
    r"^(GIR 0AA|[A-PR-UWYZ]([0-9]{1,2}|([A-HK-Y][0-9]([0-9ABEHMNPRV-Y])?)|[0-9][A-HJKPS-UW])"
    r" [0-9][ABD-HJLNP-UW-Z]{2})$"
)


@dataclass
class CleaningStats:
    """Counters collected while cleaning, used for the data-quality report."""

    rows_in: int = 0
    rows_out: int = 0
    nulls_before: dict[str, int] = field(default_factory=dict)
    nulls_after: dict[str, int] = field(default_factory=dict)
    dropped_missing_required: int = 0
    dropped_bad_price: int = 0
    dropped_deleted_records: int = 0
    duplicates_removed: int = 0
    changed_records_applied: int = 0
    unknown_code_values: dict[str, int] = field(default_factory=dict)
    invalid_postcodes: int = 0
    low_price_outliers: int = 0
    iqr_outliers: int = 0
    outliers_total: int = 0
    iqr_bounds: tuple[float, float] = (0.0, 0.0)
    price_summary: dict[str, float] = field(default_factory=dict)
    date_min: str = ""
    date_max: str = ""


def normalise_postcode(series: pd.Series) -> pd.Series:
    """Uppercase, strip, and format postcodes as ``OUTWARD INWARD`` (single space)."""
    squashed = series.astype("string").str.upper().str.replace(r"\s+", "", regex=True)
    out = squashed.where(squashed.str.len().between(5, 7))
    return (out.str[:-3] + " " + out.str[-3:]).astype("string")


def is_valid_postcode(series: pd.Series) -> pd.Series:
    """Boolean mask: postcode matches the UK pattern (null -> False)."""
    return series.astype("string").str.match(POSTCODE_RE).fillna(False).astype(bool)


def postcode_district(series: pd.Series) -> pd.Series:
    """Outward code of a normalised postcode, e.g. ``SW1A 1AA`` -> ``SW1A``."""
    return series.astype("string").str.split(" ").str[0]


def read_raw(paths: list[Path], columns: list[str]) -> pd.DataFrame:
    """Read headerless Price Paid CSVs into a single all-string DataFrame."""
    frames = []
    for path in paths:
        logger.info("Reading %s", path)
        frames.append(
            pd.read_csv(path, header=None, names=columns, dtype=str, keep_default_na=False)
        )
    df = pd.concat(frames, ignore_index=True)
    logger.info("Read %d raw rows from %d file(s)", len(df), len(paths))
    return df


def _clean_text(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace, collapse repeats, uppercase and convert empty strings to NA."""
    for col in ["transaction_id", "postcode", *CODE_COLUMNS, *TEXT_COLUMNS]:
        s = df[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        df[col] = s.replace("", pd.NA).str.upper()
    df["transaction_id"] = df["transaction_id"].str.strip("{}")
    return df


def _flag_outliers(df: pd.DataFrame, cfg: Config, stats: CleaningStats) -> pd.DataFrame:
    """Add outlier flag columns; rows are flagged, never deleted."""
    df["is_low_price"] = df["price"] < cfg.min_price
    log_price = np.log10(df["price"].clip(lower=1))
    q1, q3 = log_price.quantile(0.25), log_price.quantile(0.75)
    iqr = q3 - q1
    lo, hi = q1 - cfg.iqr_multiplier * iqr, q3 + cfg.iqr_multiplier * iqr
    df["is_iqr_outlier"] = (log_price < lo) | (log_price > hi)
    df["is_outlier"] = df["is_low_price"] | df["is_iqr_outlier"]
    stats.iqr_bounds = (float(10**lo), float(10**hi))
    stats.low_price_outliers = int(df["is_low_price"].sum())
    stats.iqr_outliers = int(df["is_iqr_outlier"].sum())
    stats.outliers_total = int(df["is_outlier"].sum())
    return df


def clean(raw: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, CleaningStats]:
    """Clean raw Price Paid Data.

    Steps: normalise text, enforce dtypes, parse dates, standardise postcodes,
    map codes to labels, apply A/C/D record status, de-duplicate, drop rows
    missing required fields, and flag price outliers.

    Returns the cleaned frame and a :class:`CleaningStats` summary.
    """
    stats = CleaningStats(rows_in=len(raw))
    df = raw.copy()
    blank = df.replace("", pd.NA)
    stats.nulls_before = {c: int(v) for c, v in blank.isna().sum().items()}

    df = _clean_text(df)

    # dtypes
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["date_of_transfer"] = pd.to_datetime(df["date_of_transfer"], errors="coerce").dt.normalize()

    # required fields
    missing_required = df[REQUIRED_COLUMNS].isna().any(axis=1)
    bad_price = (df["price"] <= 0) & ~missing_required
    stats.dropped_missing_required = int(missing_required.sum())
    stats.dropped_bad_price = int(bad_price.sum())
    df = df[~(missing_required | bad_price)].copy()
    df["price"] = df["price"].astype("int64")

    # record status: D = deleted, C = changed (latest wins), A = added
    df["record_status"] = df["record_status"].fillna("A")
    deleted_ids = set(df.loc[df["record_status"] == "D", "transaction_id"])
    stats.dropped_deleted_records = int(df["transaction_id"].isin(deleted_ids).sum())
    df = df[~df["transaction_id"].isin(deleted_ids)]

    # duplicates: keep the last occurrence per transaction (changes are appended later)
    before = len(df)
    df = df.drop_duplicates("transaction_id", keep="last")
    stats.duplicates_removed = before - len(df)
    stats.changed_records_applied = int((df["record_status"] == "C").sum())

    # postcodes
    df["postcode"] = normalise_postcode(df["postcode"])
    df["is_valid_postcode"] = is_valid_postcode(df["postcode"])
    df["postcode_district"] = postcode_district(df["postcode"].where(df["is_valid_postcode"]))
    stats.invalid_postcodes = int((~df["is_valid_postcode"]).sum())

    # code -> label
    for col, mapping, label in [
        ("property_type", PROPERTY_TYPE_MAP, "property_type_label"),
        ("old_new", OLD_NEW_MAP, "old_new_label"),
        ("duration", DURATION_MAP, "duration_label"),
    ]:
        df[label] = df[col].map(mapping)
        unknown = df[col].notna() & df[label].isna()
        if unknown.any():
            stats.unknown_code_values[col] = int(unknown.sum())
        df[label] = df[label].fillna("Unknown")

    for col in ("town_city", "district", "county"):
        df[col] = df[col].fillna("UNKNOWN")

    df = _flag_outliers(df, cfg, stats)

    df = df.sort_values(["date_of_transfer", "transaction_id"]).reset_index(drop=True)
    stats.rows_out = len(df)
    stats.nulls_after = {c: int(v) for c, v in df.isna().sum().items() if v}
    stats.price_summary = {k: float(v) for k, v in df["price"].describe(percentiles=[0.5]).items()}
    if len(df):
        stats.date_min = df["date_of_transfer"].min().strftime("%Y-%m-%d")
        stats.date_max = df["date_of_transfer"].max().strftime("%Y-%m-%d")
    logger.info(
        "Cleaned %d -> %d rows (%d duplicates, %d deleted, %d outliers flagged)",
        stats.rows_in,
        stats.rows_out,
        stats.duplicates_removed,
        stats.dropped_deleted_records,
        stats.outliers_total,
    )
    return df, stats


def write_quality_report(stats: CleaningStats, path: Path, sample: bool = False) -> Path:
    """Write the data-quality report as Markdown."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def pct(n: int) -> str:
        return f"{100 * n / stats.rows_in:.3f}%" if stats.rows_in else "n/a"

    lines = [
        "# Data Quality Report",
        "",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M}",
    ]
    if sample:
        lines += ["", "**Note: generated from a SAMPLE run, not the full dataset.**"]
    lines += [
        "",
        "## Row counts",
        "",
        "| Metric | Rows | % of input |",
        "|---|---:|---:|",
        f"| Rows in | {stats.rows_in:,} | 100% |",
        f"| Rows out | {stats.rows_out:,} | {pct(stats.rows_out)} |",
        f"| Dropped: missing transaction id, price or date | "
        f"{stats.dropped_missing_required:,} | {pct(stats.dropped_missing_required)} |",
        f"| Dropped: non-positive price | {stats.dropped_bad_price:,} | "
        f"{pct(stats.dropped_bad_price)} |",
        f"| Dropped: record_status = D (deleted) | {stats.dropped_deleted_records:,} | "
        f"{pct(stats.dropped_deleted_records)} |",
        f"| Duplicates removed (same transaction_id) | {stats.duplicates_removed:,} | "
        f"{pct(stats.duplicates_removed)} |",
        f"| Change records (C) applied | {stats.changed_records_applied:,} | "
        f"{pct(stats.changed_records_applied)} |",
        "",
        "## Validity and outliers (flagged, not removed)",
        "",
        "| Metric | Rows |",
        "|---|---:|",
        f"| Invalid / missing postcodes | {stats.invalid_postcodes:,} |",
        f"| Price below minimum threshold | {stats.low_price_outliers:,} |",
        f"| Log-price IQR outliers | {stats.iqr_outliers:,} |",
        f"| Total outlier-flagged rows | {stats.outliers_total:,} |",
        "",
        f"Log-price IQR fence: £{stats.iqr_bounds[0]:,.0f} to £{stats.iqr_bounds[1]:,.0f}.",
        "",
        "## Null counts per column",
        "",
        "| Column | Before cleaning | After cleaning |",
        "|---|---:|---:|",
    ]
    for col, before in stats.nulls_before.items():
        lines.append(f"| {col} | {before:,} | {stats.nulls_after.get(col, 0):,} |")
    lines += [
        "",
        "Empty strings count as null. Optional address fields such as `saon` and `locality` "
        "are legitimately empty for many properties. Missing town, district and county are "
        "filled with `UNKNOWN` after cleaning.",
        "",
    ]
    if stats.unknown_code_values:
        lines += ["## Unknown category codes", ""]
        lines += [f"- `{k}`: {v:,} rows" for k, v in stats.unknown_code_values.items()]
        lines.append("")
    ps = stats.price_summary
    if ps:
        lines += [
            "## Price summary (cleaned data)",
            "",
            f"- Date range: {stats.date_min} to {stats.date_max}",
            f"- Mean: £{ps['mean']:,.0f}, median: £{ps['50%']:,.0f}",
            f"- Min: £{ps['min']:,.0f}, max: £{ps['max']:,.0f}",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote data-quality report to %s", path)
    return path


def sample_frame(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """Random sample of at most ``n`` raw rows (reproducible)."""
    return df if len(df) <= n else df.sample(n=n, random_state=seed).reset_index(drop=True)
