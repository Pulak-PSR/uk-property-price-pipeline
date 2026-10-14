"""Unit tests for the cleaning stage."""

import numpy as np
import pandas as pd

from uk_property_pipeline.clean import (
    clean,
    is_valid_postcode,
    normalise_postcode,
    postcode_district,
    write_quality_report,
)


def test_normalise_postcode_formats_case_and_spacing():
    s = pd.Series(["sw1a  1aa", " m201bs", "CF40 2PW", None, "TOOLONGPOSTCODE"])
    out = normalise_postcode(s)
    assert out.iloc[0] == "SW1A 1AA"
    assert out.iloc[1] == "M20 1BS"
    assert out.iloc[2] == "CF40 2PW"
    assert pd.isna(out.iloc[3])
    assert pd.isna(out.iloc[4])


def test_is_valid_postcode():
    s = pd.Series(["SW1A 1AA", "M1 1AE", "GIR 0AA", "12345", "AA 1", None])
    assert is_valid_postcode(s).tolist() == [True, True, True, False, False, False]


def test_postcode_district():
    assert postcode_district(pd.Series(["SW1A 1AA", "M20 1BS"])).tolist() == ["SW1A", "M20"]


def test_row_accounting(cleaned):
    df, stats = cleaned
    assert stats.rows_in == 12
    assert stats.dropped_missing_required == 1  # empty price
    assert stats.dropped_deleted_records == 2  # id ...05 (A + D)
    assert stats.duplicates_removed == 1  # id ...04 (A then C)
    assert stats.rows_out == len(df) == 8


def test_change_record_wins(cleaned):
    df, stats = cleaned
    row = df[df["transaction_id"].str.endswith("000000000004")].iloc[0]
    assert row["price"] == 310000
    assert row["record_status"] == "C"
    assert stats.changed_records_applied == 1


def test_deleted_record_removed(cleaned):
    df, _ = cleaned
    assert not df["transaction_id"].str.endswith("000000000005").any()


def test_labels_mapped(cleaned):
    df, _ = cleaned
    row = df[df["transaction_id"].str.endswith("000000000001")].iloc[0]
    assert row["property_type_label"] == "Detached"
    assert row["old_new_label"] == "Existing"
    assert row["duration_label"] == "Freehold"
    new_build = df[df["transaction_id"].str.endswith("000000000002")].iloc[0]
    assert new_build["old_new_label"] == "New Build"


def test_text_trimmed_and_braces_removed(cleaned):
    df, _ = cleaned
    assert not df["transaction_id"].str.contains("[{}]", regex=True).any()
    assert "BIRMINGHAM" in set(df["town_city"])


def test_invalid_postcodes_flagged_not_dropped(cleaned):
    df, stats = cleaned
    assert stats.invalid_postcodes == 2
    assert (~df["is_valid_postcode"]).sum() == 2
    assert df.loc[df["is_valid_postcode"], "postcode_district"].notna().all()


def test_low_price_flagged_not_dropped(cleaned):
    df, stats = cleaned
    row = df[df["price"] == 1]
    assert len(row) == 1
    assert row.iloc[0]["is_low_price"]
    assert row.iloc[0]["is_outlier"]
    assert stats.low_price_outliers == 1


def test_missing_location_filled(cleaned):
    df, _ = cleaned
    row = df[df["transaction_id"].str.endswith("000000000009")].iloc[0]
    assert row["town_city"] == "UNKNOWN"


def test_iqr_outlier_flagged(cfg, raw_df):
    rng = np.random.default_rng(0)
    base = raw_df.iloc[[0]]
    rows = pd.concat([base] * 200, ignore_index=True)
    rows["transaction_id"] = [f"{{ID-{i:04d}-{'X' * 24}}}" for i in range(200)]
    rows["price"] = rng.integers(150_000, 400_000, 200).astype(str)
    rows.loc[0, "price"] = "900000000"
    df, stats = clean(rows, cfg)
    assert df.loc[df["price"] == 900_000_000, "is_iqr_outlier"].all()
    assert stats.iqr_outliers >= 1


def test_quality_report_written(cleaned, tmp_path):
    _, stats = cleaned
    path = write_quality_report(stats, tmp_path / "dq.md")
    text = path.read_text(encoding="utf-8")
    assert "Rows in" in text and "Null counts per column" in text
