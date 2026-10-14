"""Command-line entry point that runs the pipeline stages."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from .clean import clean, read_raw, sample_frame, write_quality_report
from .config import Config, load_config
from .extract import extract, raw_path
from .load import get_engine, load
from .logging_setup import setup_logging
from .transform import load_region_lookup, transform
from .validate import DataValidationError, validate

logger = logging.getLogger(__name__)

STAGES = ["extract", "clean", "validate", "transform", "load"]
TABLES = ["dim_date", "dim_property", "dim_location", "fact_sales"]


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    p = argparse.ArgumentParser(
        prog="ukprop", description="UK Price Paid Data pipeline: extract, clean, validate, "
        "transform and load into a SQL star schema."
    )  # fmt: skip
    p.add_argument("--years", nargs="+", type=int, help="years to process (default: from config)")
    p.add_argument(
        "--stage",
        choices=[*STAGES, "all"],
        default="all",
        help="run a single stage (reads the previous stage's saved output) or 'all'",
    )
    p.add_argument(
        "--sample",
        action="store_true",
        help="quick test run: random sample of rows (size set in config), outputs kept separate",
    )
    p.add_argument("--config", type=Path, help="path to an alternative config.yaml")
    p.add_argument("--force-download", action="store_true", help="re-download existing files")
    p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return p


def _cleaned_path(cfg: Config, sample: bool) -> Path:
    return cfg.processed_dir / f"cleaned{'_sample' if sample else ''}.parquet"


def _table_path(cfg: Config, name: str, sample: bool) -> Path:
    return cfg.processed_dir / f"{name}{'_sample' if sample else ''}.parquet"


def run_clean(cfg: Config, years: list[int], sample: bool) -> pd.DataFrame:
    """Read raw CSVs, clean them, save parquet and the quality report."""
    raw = read_raw([raw_path(cfg, y) for y in years], cfg.columns)
    if sample:
        raw = sample_frame(raw, cfg.sample_rows)
        logger.info("Sample mode: using %d random rows", len(raw))
    df, stats = clean(raw, cfg)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_cleaned_path(cfg, sample), index=False)
    report = cfg.reports_dir / (
        "data_quality_report_sample.md" if sample else "data_quality_report.md"
    )
    write_quality_report(stats, report, sample=sample)
    return df


def run_transform(cfg: Config, df: pd.DataFrame, sample: bool) -> dict[str, pd.DataFrame]:
    """Build the star schema and save each table as parquet."""
    tables = transform(df, load_region_lookup(cfg.region_lookup))
    for name, table in tables.items():
        table.to_parquet(_table_path(cfg, name, sample), index=False)
    return tables


def run(args: argparse.Namespace) -> None:
    """Execute the requested stage(s)."""
    cfg = load_config(args.config)
    years = args.years or cfg.years
    stages = STAGES if args.stage == "all" else [args.stage]
    df: pd.DataFrame | None = None
    tables: dict[str, pd.DataFrame] | None = None

    for stage in stages:
        started = time.perf_counter()
        logger.info("=== Stage: %s ===", stage)
        if stage == "extract":
            extract(cfg, years, force=args.force_download)
        elif stage == "clean":
            df = run_clean(cfg, years, args.sample)
        elif stage == "validate":
            df = df if df is not None else pd.read_parquet(_cleaned_path(cfg, args.sample))
            validate(df)
        elif stage == "transform":
            df = df if df is not None else pd.read_parquet(_cleaned_path(cfg, args.sample))
            tables = run_transform(cfg, df, args.sample)
        elif stage == "load":
            tables = tables or {
                n: pd.read_parquet(_table_path(cfg, n, args.sample)) for n in TABLES
            }
            load(tables, get_engine())
        logger.info("Stage %s finished in %.1fs", stage, time.perf_counter() - started)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    try:
        run(args)
    except DataValidationError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:
        logger.exception("Pipeline failed")
        return 1
    logger.info("Pipeline complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
