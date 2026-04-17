"""
handlers/play.py — /play command.

Resolution order for the user's input:
  1. Spotify URL          → resolve via spotify service → list of YT-backed tracks
  2. SoundCloud URL       → resolve via soundcloud service
  3. YouTube URL          → resolve via youtube service
  4. Other direct URL     → pass straight to yt-dlp via youtube.get_track()
  5. Plain text query     → YouTube search
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import config
from bot.database import get_user_lang, upsert_user
from bot.locales.i18n import get_text
from bot.player.music_player import music_player
from bot.player.queue_manager import queue_manager
from bot.services import soundcloud as sc
from bot.services import spotify as sp
from bot.services import youtube as yt
from bot.utils.decorators import error_handler, group_only, rate_limit
from bot.utils.formatters import (
    format_duration,
    is_soundcloud_url,
    is_spotify_url,
    is_url,
    is_youtube_url,
)
from bot.utils.logger import get_logger

log = get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_track_meta(track: dict, user: object, chat_id: int) -> dict:
    """Stamp the requester info onto the track dict."""
    track = dict(track)   # shallow copy so we don't mutate cached objects
    track["requested_by"] = user.mention if hasattr(user, "mention") else str(user.id)
    track["requested_by_id"] = user.id
    track["chat_id"] = chat_id
    return track


# ── /play ─────────────────────────────────────────────────────────────────────


@Client.on_message(filters.command("play") & filters.group)
@error_handler
@rate_limit(max_calls=5, window=30)
@group_only
async def cmd_play(client: Client, message: Message):
    """
    /play <query | URL>

    Accepts:
      - YouTube URL (video / playlist)
      - Spotify URL (track / album / playlist)
      - SoundCloud URL (track / set)
      - Any other direct audio URL
      - Plain search query (resolved via YouTube)
    """
    user = message.from_user
    chat_id = message.chat.id
    lang = await get_user_lang(user.id)

    # Register user silently
    await upsert_user(
        user.id,
        {
            "first_name": user.first_name or "",
            "username": user.username or "",
        },
    )

    # ── Extract query ──────────────────────────────────────────────────────
    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "❌ Please provide a song name or URL.\n\nUsage: `/play <query or URL>`",
            quote=True,
        )
        return

    query = parts[1].strip()

    processing_msg = await message.reply_text(
        get_text("processing", lang=lang),
        quote=True,
    )

    # ── Route by source type ───────────────────────────────────────────────

    try:
        if is_spotify_url(query):
            await _handle_spotify(client, message, processing_msg, query, user, chat_id, lang)

        elif is_soundcloud_url(query):
            await _handle_soundcloud(client, message, processing_msg, query, user, chat_id, lang)

        elif is_youtube_url(query) and "list=" in query:
            # YouTube playlist
            await _handle_youtube_playlist(client, message, processing_msg, query, user, chat_id, lang)

        elif is_url(query):
            # Generic URL (YouTube single video, direct audio link, etc.)
            await _handle_url(client, message, processing_msg, query, user, chat_id, lang)

        else:
            # Plain text search → YouTube
            await _handle_search(client, message, processing_msg, query, user, chat_id, lang)

    except Exception as e:
        log.exception(f"[{chat_id}] /play error: {e}")
        await processing_msg.edit_text(get_text("error_generic", lang=lang))


# ── Source-specific handlers ──────────────────────────────────────────────────


async def _handle_spotify(client, message, processing_msg, url, user, chat_id, lang):
    """Resolve Spotify → YouTube tracks and enqueue them."""
    parsed = sp.parse_spotify_url(url)
    if not parsed:
        await processing_msg.edit_text(get_text("error_generic", lang=lang))
        return

    kind, _ = parsed

    if kind == "track":
        await processing_msg.edit_text(get_text("spotify_track", lang=lang))
    else:
        await processing_msg.edit_text(
            get_text("spotify_playlist", lang=lang, count="…")
        )

    tracks = await sp.resolve_url(url)
    if not tracks:
        await processing_msg.edit_text(get_text("no_results", lang=lang, query=url))
        return

    tracks = [_make_track_meta(t, user, chat_id) for t in tracks]
    await _enqueue_tracks(client, message, processing_msg, tracks, chat_id, lang)


async def _handle_soundcloud(client, message, processing_msg, url, user, chat_id, lang):
    """Resolve SoundCloud URL (single track or set) and enqueue."""
    if sc.is_soundcloud_playlist(url):
        await processing_msg.edit_text("🎵 Fetching SoundCloud playlist…")
        tracks = await sc.get_playlist(url, max_tracks=config.MAX_PLAYLIST_SIZE)
    else:
        track = await sc.get_track(url)
        tracks = [track] if track else []

    if not tracks:
        await processing_msg.edit_text(get_text("no_results", lang=lang, query=url))
        return

    tracks = [_make_track_meta(t, user, chat_id) for t in tracks]
    await _enqueue_tracks(client, message, processing_msg, tracks, chat_id, lang)


async def _handle_youtube_playlist(client, message, processing_msg, url, user, chat_id, lang):
    """Resolve a YouTube playlist URL and bulk-enqueue."""
    await processing_msg.edit_text("🎵 Fetching YouTube playlist…")
    tracks = await yt.get_playlist(url, max_tracks=config.MAX_PLAYLIST_SIZE)

    if not tracks:
        await processing_msg.edit_text(get_text("no_results", lang=lang, query=url))
        return

    tracks = [_make_track_meta(t, user, chat_id) for t in tracks]
    await _enqueue_tracks(client, message, processing_msg, tracks, chat_id, lang)


async def _handle_url(client, message, processing_msg, url, user, chat_id, lang):
    """Resolve a generic/direct URL via yt-dlp."""
    track = await yt.get_track(url)
    if not track:
        await processing_msg.edit_text(get_text("no_results", lang=lang, query=url))
        return

    track = _make_track_meta(track, user, chat_id)
    await _enqueue_tracks(client, message, processing_msg, [track], chat_id, lang)


async def _handle_search(client, message, processing_msg, query, user, chat_id, lang):
    """YouTube keyword search → top result → enqueue."""
    await processing_msg.edit_text(get_text("searching", lang=lang, query=query))
    track = await yt.search(query)
    if not track:
        await processing_msg.edit_text(get_text("no_results", lang=lang, query=query))
        return

    track = _make_track_meta(track, user, chat_id)
    await _enqueue_tracks(client, message, processing_msg, [track], chat_id, lang)


# ── Common enqueue logic ──────────────────────────────────────────────────────


async def _enqueue_tracks(client, message, processing_msg, tracks, chat_id, lang):
    """
    Given a resolved list of tracks:
      - If nothing is playing → start playback with tracks[0], queue rest
      - If something is playing → add all to queue
    """
    if not tracks:
        await processing_msg.edit_text(get_text("queue_empty", lang=lang))
        return

    is_active = music_player.is_active(chat_id)

    if not is_active:
        # Play the first track immediately
        first = tracks[0]
        rest = tracks[1:]

        try:
            # music_player.play() won't re-queue if nothing is playing
            await music_player.play(chat_id, first)
        except Exception as e:
            log.error(f"[{chat_id}] Failed to start playback: {e}")
            await processing_msg.edit_text(get_text("error_generic", lang=lang))
            return

        # Queue the rest
        if rest:
            added = await queue_manager.add_many(chat_id, rest)
            await processing_msg.edit_text(
                f"▶️ Playing: **{first.get('title', 'Unknown')}**\n"
                f"📋 {added} more track(s) added to queue."
            )
        else:
            await processing_msg.delete()   # NP card already sent by music_player

    else:
        # Already playing — bulk-add
        try:
            added = await queue_manager.add_many(chat_id, tracks)
        except ValueError as e:
            await processing_msg.edit_text(f"❌ {e}")
            return

        if added == 1:
            t = tracks[0]
            pos = await queue_manager.length(chat_id)
            await processing_msg.edit_text(
                get_text(
                    "added_to_queue",
                    lang=lang,
                    title=t.get("title", "Unknown"),
                    duration=format_duration(t.get("duration", 0)),
                    position=pos,
                )
            )
        else:
            await processing_msg.edit_text(
                f"✅ **{added}** tracks added to queue!"
            )
