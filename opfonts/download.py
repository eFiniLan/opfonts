"""Font downloader with local caching and retry."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import BuildConfig

log = logging.getLogger(__name__)

_USER_AGENT = "opfonts/0.1"
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # seconds


def _download(url: str, dest: Path) -> None:
    """Download url to dest with retries."""
    log.info("Downloading %s", url)
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            log.debug("Saved %s (%d bytes)", dest, len(data))
            return
        except (HTTPError, URLError, OSError) as exc:
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Failed to download {url} after {_MAX_RETRIES} attempts") from exc
            log.warning("Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, url, exc)
            time.sleep(_RETRY_DELAY * attempt)


def _cache_path(cache_dir: Path, font_name: str) -> Path:
    return cache_dir / font_name


def ensure_font(cache_dir: Path, font_name: str, url: str) -> Path:
    """Return local path to a font, downloading if needed."""
    cached = _cache_path(cache_dir, font_name)
    if cached.exists():
        log.debug("Cache hit: %s", cached)
        return cached
    _download(url, cached)
    return cached


def get_download_plan(config: BuildConfig) -> list[tuple[str, str, Path]]:
    """Return (name, url, cache_path) tuples for all fonts that would be downloaded."""
    plan: list[tuple[str, str, Path]] = []
    for script in config.scripts:
        if not script.enabled:
            continue
        cached = _cache_path(config.cache_dir, script.font)
        plan.append((script.font, script.url, cached))
    return plan
