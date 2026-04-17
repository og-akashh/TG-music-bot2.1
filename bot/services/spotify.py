"""
spotify.py — Spotify metadata + YouTube stream resolution.

Flow:
  1. Authenticate with Spotify API via client_credentials
  2. Fetch track/playlist/album metadata
  3. Map each track → YouTube search → stream URL
"""

import asyncio
import base64
import re
from typing import Dict, List, Optional

import httpx

from bot.config import config
from bot.database import cache_get, cache_set
from bot.services import youtube as yt
from bot.utils.logger import get_logger

log = get_logger(__name__)

_TOKEN_CACHE_KEY = "spotify_access_token"
_BASE_URL = "https://api.spotify.com/v1"


# ── Authentication ────────────────────────────────────────────────────────────

async def _get_access_token() -> Optional[str]:
    cached = await cache_get(_TOKEN_CACHE_KEY)
    if cached:
        return cached

    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        log.warning("Spotify credentials not configured.")
        return None

    creds = base64.b64encode(
        f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        ttl = data.get("expires_in", 3600) - 60
        await cache_set(_TOKEN_CACHE_KEY, token, ttl=ttl)
        return token


async def _spotify_get(endpoint: str) -> Optional[dict]:
    token = await _get_access_token()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_BASE_URL}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        log.error(f"Spotify API error {resp.status_code}: {endpoint}")
        return None


# ── URL parsing ───────────────────────────────────────────────────────────────

def parse_spotify_url(url: str) -> Optional[tuple]:
    """Returns (type, id) where type ∈ {'track', 'album', 'playlist'}."""
    pattern = r"spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2)
    return None


# ── Metadata fetchers ─────────────────────────────────────────────────────────

async def get_track(spotify_id: str) -> Optional[dict]:
    data = await _spotify_get(f"tracks/{spotify_id}")
    if not data:
        return None
    return _normalise_track(data)


async def get_album(spotify_id: str) -> Optional[List[dict]]:
    data = await _spotify_get(f"albums/{spotify_id}/tracks?limit=50")
    if not data:
        return None
    # Album tracks don't include full metadata; re-fetch each (or use simplified)
    tracks = []
    for item in data.get("items", []):
        tracks.append({
            "spotify_id": item["id"],
            "title": item["name"],
            "artist": ", ".join(a["name"] for a in item.get("artists", [])),
            "duration": item.get("duration_ms", 0) // 1000,
            "source": "spotify",
        })
    return tracks


async def get_playlist(spotify_id: str, max_tracks: int = 50) -> Optional[List[dict]]:
    data = await _spotify_get(f"playlists/{spotify_id}/tracks?limit={max_tracks}")
    if not data:
        return None
    tracks = []
    for item in data.get("items", []):
        track = item.get("track")
        if track:
            tracks.append(_normalise_track(track))
    return tracks


def _normalise_track(data: dict) -> dict:
    artists = ", ".join(a["name"] for a in data.get("artists", []))
    album = data.get("album", {})
    thumbnail = ""
    images = album.get("images") or []
    if images:
        thumbnail = images[0].get("url", "")

    return {
        "spotify_id": data.get("id", ""),
        "title": data.get("name", "Unknown"),
        "artist": artists,
        "duration": data.get("duration_ms", 0) // 1000,
        "thumbnail": thumbnail,
        "source": "spotify",
    }


# ── Resolution: Spotify → YouTube ────────────────────────────────────────────

async def resolve_to_youtube(spotify_track: dict) -> Optional[dict]:
    """Map a Spotify track dict to a YouTube track dict."""
    query = f"{spotify_track['title']} {spotify_track['artist']} official audio"
    yt_track = await yt.search(query)
    if yt_track:
        # Prefer Spotify metadata (title, artist, thumbnail) if richer
        yt_track["title"] = spotify_track.get("title") or yt_track["title"]
        yt_track["artist"] = spotify_track.get("artist") or yt_track["artist"]
        if spotify_track.get("thumbnail"):
            yt_track["thumbnail"] = spotify_track["thumbnail"]
        yt_track["spotify_id"] = spotify_track.get("spotify_id", "")
    return yt_track


async def resolve_url(url: str) -> List[dict]:
    """
    Given any Spotify URL, return a list of resolved YouTube-backed track dicts.
    """
    parsed = parse_spotify_url(url)
    if not parsed:
        return []
    kind, sid = parsed

    if kind == "track":
        sp_track = await get_track(sid)
        if not sp_track:
            return []
        yt_track = await resolve_to_youtube(sp_track)
        return [yt_track] if yt_track else []

    elif kind == "album":
        sp_tracks = await get_album(sid) or []
    elif kind == "playlist":
        sp_tracks = await get_playlist(sid) or []
    else:
        return []

    # Resolve concurrently (but throttle to avoid hammering YT search)
    results = []
    sem = asyncio.Semaphore(3)

    async def resolve_one(t):
        async with sem:
            return await resolve_to_youtube(t)

    tasks = [asyncio.create_task(resolve_one(t)) for t in sp_tracks]
    for coro in asyncio.as_completed(tasks):
        track = await coro
        if track:
            results.append(track)

    return results
