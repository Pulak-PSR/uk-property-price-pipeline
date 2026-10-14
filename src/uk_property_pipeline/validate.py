"""Stage 3: schema and business-rule validation of cleaned data."""

from __future__ import annotations

import logging

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

from .clean import DURATION_MAP, OLD_NEW_MAP, PROPERTY_TYPE_MAP

logger = logging.getLogger(__name__)

EARLIEST_DATE = pd.Timestamp("1995-01-01")
MAX_INVALID_POSTCODE_RATE = 0.02


class DataValidationError(RuntimeError):
    """Raised when cleaned data fails schema or business-rule checks."""


def build_schema() -> DataFrameSchema:
    """Pandera schema for the cleaned dataset."""
    return DataFrameSchema(
        {
            "transaction_id": Column(
                str, Check.str_length(min_value=36, max_value=36), unique=True
            ),
            "price": Column(int, Check.gt(0)),
            "date_of_transfer": Column(
                "datetime64[us]",
                [
                    Check.ge(EARLIEST_DATE, error="date before 1995 (start of Price Paid Data)"),
                    Check(
                        lambda s: s <= pd.Timestamp.today().normalize(),
                        error="date of transfer is in the future",
                    ),
                ],
                coerce=True,
            ),
            "property_type": Column(str, Check.isin(list(PROPERTY_TYPE_MAP)), nullable=True),
            "old_new": Column(str, Check.isin(list(OLD_NEW_MAP)), nullable=True),
            "duration": Column(str, Check.isin(list(DURATION_MAP)), nullable=True),
            "postcode": Column(str, nullable=True),
            "is_valid_postcode": Column(bool),
            "is_outlier": Column(bool),
            "town_city": Column(str),
            "district": Column(str),
            "county": Column(str),
        },
        coerce=False,
        strict=False,
    )


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a cleaned frame, raising :class:`DataValidationError` with clear messages.

    Checks the pandera schema (types, domains, uniqueness) and business rules
    (non-empty, postcode quality rate within tolerance).
    """
    problems: list[str] = []
    if df.empty:
        raise DataValidationError("Cleaned dataset is empty; nothing to load.")

    try:
        build_schema().validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        fc = exc.failure_cases
        for (column, check), group in fc.groupby(["column", "check"], dropna=False):
            examples = group["failure_case"].head(3).tolist()
            problems.append(
                f"column '{column}' failed '{check}' on {len(group)} value(s), e.g. {examples}"
            )

    invalid_rate = 1 - df["is_valid_postcode"].mean()
    if invalid_rate > MAX_INVALID_POSTCODE_RATE:
        problems.append(
            f"invalid postcode rate {invalid_rate:.2%} exceeds "
            f"limit {MAX_INVALID_POSTCODE_RATE:.0%}"
        )

    if problems:
        message = "Data validation failed:\n  - " + "\n  - ".join(problems)
        logger.error(message)
        raise DataValidationError(message)
    logger.info("Validation passed for %d rows", len(df))
    return df
