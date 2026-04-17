"""
lyrics.py — Fetch song lyrics via Genius API.

Falls back to a simple web scrape if API token is unavailable.
"""

import re
from typing import Optional

import httpx

from bot.config import config
from bot.database import cache_get, cache_set
from bot.utils.logger import get_logger

log = get_logger(__name__)

_GENIUS_BASE = "https://api.genius.com"
_CACHE_TTL = 3600 * 24   # lyrics don't change


async def _genius_search(query: str) -> Optional[dict]:
    if not config.GENIUS_API_TOKEN:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_GENIUS_BASE}/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {config.GENIUS_API_TOKEN}"},
        )
        if resp.status_code != 200:
            return None
        hits = resp.json().get("response", {}).get("hits", [])
        return hits[0]["result"] if hits else None


async def _scrape_lyrics(genius_url: str) -> Optional[str]:
    """Scrape lyrics text from a Genius page (simplified)."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(genius_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return None
        html = resp.text
        # Extract text between [Verse] / [Chorus] tags (rough heuristic)
        pattern = re.compile(r'<div[^>]*data-lyrics-container[^>]*>(.*?)</div>', re.DOTALL)
        matches = pattern.findall(html)
        if not matches:
            return None
        raw = " ".join(matches)
        # Strip HTML tags
        text = re.sub(r"<br\s*/?>", "\n", raw)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\[([^\]]+)\]", r"\n[\1]\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text if text else None
    except Exception as e:
        log.error(f"Lyrics scrape error: {e}")
        return None


async def get_lyrics(title: str, artist: str = "") -> Optional[str]:
    """
    Fetch lyrics for a track.

    Returns lyrics string or None if not found.
    """
    query = f"{title} {artist}".strip()
    cache_key = f"lyrics:{query.lower().replace(' ', '_')[:80]}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached or None  # empty string cached as "not found"

    hit = await _genius_search(query)
    if not hit:
        await cache_set(cache_key, "", ttl=_CACHE_TTL)
        return None

    lyrics_url = hit.get("url")
    if not lyrics_url:
        await cache_set(cache_key, "", ttl=_CACHE_TTL)
        return None

    lyrics = await _scrape_lyrics(lyrics_url)
    await cache_set(cache_key, lyrics or "", ttl=_CACHE_TTL)
    return lyrics


def chunk_lyrics(lyrics: str, max_len: int = 4000) -> list:
    """Split long lyrics into Telegram-safe chunks."""
    if len(lyrics) <= max_len:
        return [lyrics]
    chunks = []
    current = ""
    for line in lyrics.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks
