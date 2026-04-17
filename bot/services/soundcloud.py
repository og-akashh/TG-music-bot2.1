"""
soundcloud.py — SoundCloud track and playlist extraction.

yt-dlp supports SoundCloud natively, so we reuse the same
extraction pipeline with SoundCloud-specific URL detection.

Supports:
  • Single track URL  → dict
  • Playlist/set URL  → list[dict]
  • Artist page URL   → list[dict]  (up to max_tracks)
"""

import asyncio
import hashlib
from typing import Dict, List, Optional

import yt_dlp

from bot.config import config
from bot.database import cache_get, cache_set
from bot.utils.logger import get_logger

log = get_logger(__name__)

_CACHE_TTL = 3600 * 4   # SoundCloud stream URLs expire ~4 h


# ── yt-dlp options tuned for SoundCloud ──────────────────────────────────────

def _sc_opts() -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": f"{config.CACHE_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        },
    }


def _sc_flat_opts() -> dict:
    opts = _sc_opts()
    opts["extract_flat"] = True
    return opts


# ── Normalise raw yt-dlp info → our track dict ────────────────────────────────

def _normalise(info: dict) -> dict:
    stream_url = info.get("url") or ""
    if not stream_url and "formats" in info:
        fmts = [f for f in info["formats"] if f.get("acodec") != "none"]
        fmts.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        stream_url = fmts[0]["url"] if fmts else ""

    thumbnail = info.get("thumbnail") or ""
    if not thumbnail:
        thumbs = info.get("thumbnails") or []
        thumbnail = thumbs[-1].get("url", "") if thumbs else ""

    return {
        "id": info.get("id", ""),
        "title": info.get("title", "Unknown"),
        "artist": info.get("uploader") or info.get("artist") or "",
        "duration": int(info.get("duration") or 0),
        "stream_url": stream_url,
        "webpage_url": info.get("webpage_url") or info.get("url") or "",
        "thumbnail": thumbnail,
        "source": "soundcloud",
        "extractor": "SoundCloud",
    }


# ── Blocking extraction helpers (run in executor) ─────────────────────────────

def _extract_track_sync(url: str) -> Optional[dict]:
    try:
        with yt_dlp.YoutubeDL(_sc_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and "entries" in info:
                info = info["entries"][0] if info["entries"] else None
            return info
    except Exception as e:
        log.error(f"SoundCloud extraction error: {e}")
        return None


def _extract_playlist_sync(url: str, max_tracks: int) -> List[dict]:
    results = []
    try:
        with yt_dlp.YoutubeDL(_sc_flat_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            entries = info.get("entries") or [info]
            for entry in entries[:max_tracks]:
                if entry:
                    results.append({
                        "id": entry.get("id", ""),
                        "title": entry.get("title", "Unknown"),
                        "artist": entry.get("uploader") or entry.get("artist") or "",
                        "duration": int(entry.get("duration") or 0),
                        "stream_url": "",   # resolved lazily when played
                        "webpage_url": entry.get("url") or entry.get("webpage_url", ""),
                        "thumbnail": entry.get("thumbnail", ""),
                        "source": "soundcloud",
                    })
    except Exception as e:
        log.error(f"SoundCloud playlist extraction error: {e}")
    return results


def _search_sync(query: str) -> Optional[dict]:
    try:
        with yt_dlp.YoutubeDL(_sc_opts()) as ydl:
            info = ydl.extract_info(f"scsearch1:{query}", download=False)
            if info and "entries" in info:
                info = info["entries"][0] if info["entries"] else None
            return info
    except Exception as e:
        log.error(f"SoundCloud search error: {e}")
        return None


# ── Public async API ──────────────────────────────────────────────────────────

def is_soundcloud_url(url: str) -> bool:
    return "soundcloud.com" in url.lower()


def is_soundcloud_playlist(url: str) -> bool:
    """Returns True if the URL points to a set/playlist."""
    return "soundcloud.com" in url.lower() and ("/sets/" in url or "/likes" in url or "/tracks" in url)


async def get_track(url: str) -> Optional[dict]:
    """
    Fetch full info for a single SoundCloud track URL.
    Results are cached to avoid repeated API hits.
    """
    cache_key = f"sc_track:{hashlib.md5(url.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract_track_sync, url)
    if not info:
        return None

    track = _normalise(info)
    await cache_set(cache_key, track, ttl=_CACHE_TTL)
    return track


async def search(query: str) -> Optional[dict]:
    """
    Search SoundCloud for a single track matching `query`.
    """
    cache_key = f"sc_search:{hashlib.md5(query.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _search_sync, query)
    if not info:
        return None

    track = _normalise(info)
    await cache_set(cache_key, track, ttl=_CACHE_TTL)
    return track


async def get_playlist(url: str, max_tracks: int = 50) -> List[dict]:
    """
    Fetch all tracks from a SoundCloud set/playlist URL.
    Returns a list of lightweight track dicts (stream_url resolved lazily).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_playlist_sync, url, max_tracks)


async def resolve_stream_url(track: dict) -> str:
    """
    Re-fetch a fresh stream URL for an existing SoundCloud track dict.
    Needed because SoundCloud stream URLs expire.
    """
    url = track.get("webpage_url", "")
    if not url:
        return ""
    fresh = await get_track(url)
    return fresh.get("stream_url", "") if fresh else ""
