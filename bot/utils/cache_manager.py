"""
cache_manager.py — Local audio file cache eviction.

Keeps the on-disk cache under MAX_CACHE_SIZE_MB by deleting
the least-recently-used files when the limit is exceeded.

Call `maintain_cache()` periodically (e.g., every hour via a background task).
"""

import asyncio
import os
from pathlib import Path
from typing import List, Tuple

from bot.config import config
from bot.utils.logger import get_logger

log = get_logger(__name__)


def _get_cache_files() -> List[Tuple[float, int, Path]]:
    """
    Return a list of (mtime, size_bytes, path) for every file in CACHE_DIR.
    Excludes the thumbs/ subdirectory.
    """
    cache_dir = Path(config.CACHE_DIR)
    entries = []
    if not cache_dir.exists():
        return entries
    for f in cache_dir.rglob("*"):
        if f.is_file() and "thumbs" not in f.parts:
            try:
                stat = f.stat()
                entries.append((stat.st_mtime, stat.st_size, f))
            except OSError:
                pass
    return entries


def _total_size_mb(entries: List[Tuple[float, int, Path]]) -> float:
    return sum(size for _, size, _ in entries) / (1024 * 1024)


async def maintain_cache() -> None:
    """
    Evict oldest files until total cache size is under MAX_CACHE_SIZE_MB.
    Runs in a thread executor to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _evict_sync)


def _evict_sync() -> None:
    entries = _get_cache_files()
    total_mb = _total_size_mb(entries)
    max_mb = config.MAX_CACHE_SIZE_MB

    if total_mb <= max_mb:
        log.debug(f"Cache OK: {total_mb:.1f} MB / {max_mb} MB")
        return

    log.info(f"Cache eviction triggered: {total_mb:.1f} MB > {max_mb} MB")

    # Sort by oldest access time first
    entries.sort(key=lambda e: e[0])

    deleted = 0
    freed_mb = 0.0
    for mtime, size, path in entries:
        if total_mb - freed_mb <= max_mb * 0.85:   # evict down to 85%
            break
        try:
            path.unlink()
            freed_mb += size / (1024 * 1024)
            deleted += 1
            log.debug(f"Evicted: {path.name} ({size / (1024*1024):.2f} MB)")
        except OSError as e:
            log.warning(f"Could not delete {path}: {e}")

    log.info(f"Cache eviction done: removed {deleted} file(s), freed {freed_mb:.1f} MB")


async def get_cache_stats() -> dict:
    """Return current cache statistics as a dict."""
    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _get_cache_files)
    total_mb = _total_size_mb(entries)
    return {
        "file_count": len(entries),
        "total_mb": round(total_mb, 2),
        "max_mb": config.MAX_CACHE_SIZE_MB,
        "usage_percent": round(100 * total_mb / config.MAX_CACHE_SIZE_MB, 1),
    }


async def clear_cache() -> int:
    """Delete ALL files in CACHE_DIR (except thumbs). Returns count deleted."""
    entries = _get_cache_files()
    count = 0
    for _, _, path in entries:
        try:
            path.unlink()
            count += 1
        except OSError:
            pass
    log.info(f"Cache cleared: {count} file(s) deleted")
    return count
