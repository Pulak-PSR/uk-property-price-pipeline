"""Unit tests for the validation stage."""

import pandas as pd
import pytest

from uk_property_pipeline.validate import DataValidationError, validate


def test_valid_data_passes(cleaned):
    df, _ = cleaned
    # fixture deliberately has 2/8 bad postcodes, so relax by keeping only valid rows
    assert len(validate(df[df["is_valid_postcode"]])) == 6


def test_high_invalid_postcode_rate_fails(cleaned):
    df, _ = cleaned
    with pytest.raises(DataValidationError, match="invalid postcode rate"):
        validate(df)


def test_empty_fails():
    with pytest.raises(DataValidationError, match="empty"):
        validate(pd.DataFrame())


def test_duplicate_ids_fail(cleaned):
    df, _ = cleaned
    good = df[df["is_valid_postcode"]]
    dup = pd.concat([good, good.iloc[[0]]], ignore_index=True)
    with pytest.raises(DataValidationError, match="transaction_id"):
        validate(dup)


def test_negative_price_fails(cleaned):
    df, _ = cleaned
    good = df[df["is_valid_postcode"]].copy()
    good.loc[good.index[0], "price"] = -5
    with pytest.raises(DataValidationError, match="price"):
        validate(good)


def test_future_date_fails(cleaned):
    df, _ = cleaned
    good = df[df["is_valid_postcode"]].copy()
    good.loc[good.index[0], "date_of_transfer"] = pd.Timestamp("2999-01-01")
    with pytest.raises(DataValidationError, match="future"):
        validate(good)


def test_bad_code_fails(cleaned):
    df, _ = cleaned
    good = df[df["is_valid_postcode"]].copy()
    good.loc[good.index[0], "property_type"] = "Z"
    with pytest.raises(DataValidationError, match="property_type"):
        validate(good)
