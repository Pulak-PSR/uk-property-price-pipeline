"""Shared pytest fixtures."""

from pathlib import Path

import pandas as pd
import pytest

from uk_property_pipeline.clean import clean, read_raw
from uk_property_pipeline.config import Config, load_config

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ppd.csv"


@pytest.fixture(scope="session")
def cfg() -> Config:
    return load_config()


@pytest.fixture()
def raw_df(cfg: Config) -> pd.DataFrame:
    return read_raw([FIXTURE], cfg.columns)


@pytest.fixture()
def cleaned(raw_df: pd.DataFrame, cfg: Config):
    return clean(raw_df, cfg)
