"""Stage 1: download raw Price Paid Data CSVs."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from .config import Config

logger = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    """Raised when a file cannot be downloaded after all retries."""


def raw_path(cfg: Config, year: int) -> Path:
    """Local path of the raw CSV for a year."""
    return cfg.raw_dir / f"pp-{year}.csv"


def download_file(url: str, dest: Path, cfg: Config) -> Path:
    """Download ``url`` to ``dest`` with retries and progress logging.

    Writes to a ``.part`` file and renames on success, so an interrupted
    download is never mistaken for a complete one.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, cfg.retries + 1):
        try:
            logger.info("Downloading %s (attempt %d/%d)", url, attempt, cfg.retries)
            with requests.get(url, stream=True, timeout=cfg.timeout_seconds) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                done, next_report = 0, 0.1
                with part.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=cfg.chunk_bytes):
                        fh.write(chunk)
                        done += len(chunk)
                        if total and done / total >= next_report:
                            logger.info(
                                "  %s: %.0f%% (%.1f MB)", dest.name, 100 * done / total, done / 1e6
                            )
                            next_report += 0.1
            part.replace(dest)
            logger.info("Saved %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
            return dest
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            logger.warning("Download failed: %s", exc)
            if attempt < cfg.retries:
                time.sleep(cfg.backoff_seconds * attempt)
    part.unlink(missing_ok=True)
    raise DownloadError(f"Could not download {url} after {cfg.retries} attempts: {last_error}")


def extract(cfg: Config, years: list[int] | None = None, force: bool = False) -> list[Path]:
    """Download the CSV for each requested year, skipping files already present."""
    paths: list[Path] = []
    for year in years or cfg.years:
        dest = raw_path(cfg, year)
        if dest.exists() and dest.stat().st_size > 0 and not force:
            logger.info("Skipping %s (already downloaded)", dest.name)
        else:
            download_file(cfg.url_for_year(year), dest, cfg)
        paths.append(dest)
    return paths
