"""
youtube.py — YouTube search & audio extraction via yt-dlp.

Features:
  • Search by query → return top result
  • Extract direct URL → stream info
  • Smart file cache (hash-based filenames)
  • Async wrapper around blocking yt-dlp calls
  • Playlist support (returns list of tracks)
"""

import asyncio
import hashlib
import os
from typing import Dict, List, Optional

import yt_dlp

from bot.config import config
from bot.database import cache_get, cache_set
from bot.utils.logger import get_logger

log = get_logger(__name__)

_CACHE_TTL = 3600 * 6   # 6 hours for stream URLs

# ── yt-dlp options ────────────────────────────────────────────────────────────

def _ydl_opts(audio_only: bool = True) -> dict:
    opts = {
        "format": "bestaudio[ext=webm]/bestaudio/best" if audio_only else "best",
        "outtmpl": os.path.join(config.CACHE_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "source_address": "0.0.0.0",
        "postprocessors": [],
        "extract_flat": False,
        "socket_timeout": 30,
        # Throttling resistance
        "sleep_interval_requests": 0,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        },
    }
    return opts


def _search_opts() -> dict:
    opts = _ydl_opts()
    opts["extract_flat"] = "in_playlist"
    opts["quiet"] = True
    return opts


# ── Internal blocking helpers (run in executor) ───────────────────────────────

def _extract_info_sync(query_or_url: str, flat: bool = False) -> Optional[dict]:
    opts = _ydl_opts()
    if flat:
        opts["extract_flat"] = True
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            if not query_or_url.startswith("http"):
                query_or_url = f"ytsearch1:{query_or_url}"
            info = ydl.extract_info(query_or_url, download=False)
            if info and "entries" in info:
                info = info["entries"][0] if info["entries"] else None
            return info
    except Exception as e:
        log.error(f"yt-dlp extraction error: {e}")
        return None


def _extract_playlist_sync(url: str, max_tracks: int = 50) -> List[dict]:
    opts = _ydl_opts()
    opts["extract_flat"] = True
    results = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            entries = info.get("entries", [info])
            for entry in entries[:max_tracks]:
                if entry:
                    results.append(_normalise(entry))
    except Exception as e:
        log.error(f"Playlist extraction error: {e}")
    return results


def _normalise(info: dict) -> dict:
    """Map raw yt-dlp info → our standard track dict."""
    # Pick the best audio format URL
    stream_url = info.get("url") or ""
    if not stream_url and "formats" in info:
        formats = [f for f in info["formats"] if f.get("acodec") != "none"]
        formats.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        stream_url = formats[0]["url"] if formats else ""

    return {
        "id": info.get("id", ""),
        "title": info.get("title", "Unknown"),
        "artist": info.get("uploader") or info.get("artist") or "",
        "duration": int(info.get("duration") or 0),
        "stream_url": stream_url,
        "webpage_url": info.get("webpage_url") or info.get("url") or "",
        "thumbnail": (
            info.get("thumbnail")
            or (info.get("thumbnails") or [{}])[-1].get("url", "")
        ),
        "source": "youtube",
        "extractor": info.get("extractor_key", "Youtube"),
    }


# ── Public async API ──────────────────────────────────────────────────────────

async def search(query: str) -> Optional[dict]:
    """
    Search YouTube and return the top result as a track dict.
    Results are cached for 6 hours.
    """
    cache_key = f"yt_search:{hashlib.md5(query.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        log.debug(f"YT cache hit: {query}")
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract_info_sync, query)
    if not info:
        return None

    track = _normalise(info)
    await cache_set(cache_key, track, ttl=_CACHE_TTL)
    return track


async def get_track(url: str) -> Optional[dict]:
    """Extract full info from a YouTube URL."""
    cache_key = f"yt_url:{hashlib.md5(url.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract_info_sync, url)
    if not info:
        return None

    track = _normalise(info)
    await cache_set(cache_key, track, ttl=_CACHE_TTL)
    return track


async def get_playlist(url: str, max_tracks: int = 50) -> List[dict]:
    """Return a list of track dicts for a YouTube playlist."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_playlist_sync, url, max_tracks)


async def get_related(video_id: str, count: int = 5) -> List[dict]:
    """
    Fetch 'related' tracks using YouTube search with the track title.
    (yt-dlp doesn't expose recommendations; we simulate with a search.)
    """
    track = await get_track(f"https://www.youtube.com/watch?v={video_id}")
    if not track:
        return []
    query = f"{track['title']} {track['artist']} mix"
    results = []
    loop = asyncio.get_event_loop()

    def _search_n():
        opts = _search_opts()
        opts["extract_flat"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
            return (info.get("entries") or []) if info else []

    entries = await loop.run_in_executor(None, _search_n)
    for entry in entries:
        if entry and entry.get("id") != video_id:
            results.append({
                "id": entry.get("id", ""),
                "title": entry.get("title", "Unknown"),
                "artist": entry.get("uploader") or "",
                "duration": int(entry.get("duration") or 0),
                "stream_url": "",   # resolved lazily on play
                "webpage_url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                "thumbnail": "",
                "source": "youtube",
            })
    return results


async def resolve_stream_url(track: dict) -> str:
    """
    Re-fetch a fresh stream URL for a track (stream URLs expire after ~6h).
    """
    if not track.get("webpage_url"):
        return ""
    fresh = await get_track(track["webpage_url"])
    return fresh["stream_url"] if fresh else ""
