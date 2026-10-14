"""Configuration loading from config/config.yaml and .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_SQLITE_URL = f"sqlite:///{(PROJECT_ROOT / 'data' / 'processed' / 'ukproperty.db').as_posix()}"


@dataclass(frozen=True)
class Config:
    """Typed view of the YAML configuration."""

    years: list[int]
    url_template: str
    url_overrides: dict[int, str]
    raw_dir: Path
    processed_dir: Path
    reports_dir: Path
    region_lookup: Path
    columns: list[str]
    retries: int
    backoff_seconds: float
    timeout_seconds: float
    chunk_bytes: int
    min_price: int
    iqr_multiplier: float
    sample_rows: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def url_for_year(self, year: int) -> str:
        """Return the download URL for a given year."""
        if year in self.url_overrides:
            return self.url_overrides[year]
        return self.url_template.format(year=year)


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_config(path: Path | str | None = None) -> Config:
    """Load configuration from YAML (default: config/config.yaml)."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    paths, dl, cl = raw["paths"], raw["download"], raw["cleaning"]
    return Config(
        years=[int(y) for y in raw["years"]],
        url_template=raw["url_template"],
        url_overrides={int(k): v for k, v in (raw.get("url_overrides") or {}).items()},
        raw_dir=_resolve(paths["raw"]),
        processed_dir=_resolve(paths["processed"]),
        reports_dir=_resolve(paths["reports"]),
        region_lookup=_resolve(paths["region_lookup"]),
        columns=list(raw["columns"]),
        retries=int(dl["retries"]),
        backoff_seconds=float(dl["backoff_seconds"]),
        timeout_seconds=float(dl["timeout_seconds"]),
        chunk_bytes=int(dl["chunk_bytes"]),
        min_price=int(cl["min_price"]),
        iqr_multiplier=float(cl["iqr_multiplier"]),
        sample_rows=int(cl["sample_rows"]),
        raw=raw,
    )


def get_database_url() -> str:
    """Return DATABASE_URL from the environment/.env, falling back to local SQLite."""
    load_dotenv(PROJECT_ROOT / ".env")
    return os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL
