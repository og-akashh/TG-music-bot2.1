"""
handlers/playlist_handler.py — Personal playlist management.

Sub-commands (all via /playlist <action> [args]):
  /playlist list              — list all your saved playlists
  /playlist save <name>       — save the current queue as a named playlist
  /playlist load <name>       — load a saved playlist into the queue
  /playlist delete <name>     — delete a saved playlist
  /playlist show <name>       — display tracks in a saved playlist
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import config
from bot.database import (
    delete_playlist,
    get_playlist,
    get_user_lang,
    list_playlists,
    save_playlist,
)
from bot.locales.i18n import get_text
from bot.player.music_player import music_player
from bot.player.queue_manager import queue_manager
from bot.utils.decorators import error_handler, rate_limit
from bot.utils.formatters import format_duration, truncate
from bot.utils.logger import get_logger

log = get_logger(__name__)

_HELP_TEXT = (
    "💾 **Playlist Commands**\n\n"
    "`/playlist list`              — list your playlists\n"
    "`/playlist save <name>`       — save current queue\n"
    "`/playlist load <name>`       — load playlist into queue\n"
    "`/playlist show <name>`       — show tracks in a playlist\n"
    "`/playlist delete <name>`     — delete a playlist\n"
)


@Client.on_message(filters.command("playlist"))
@error_handler
@rate_limit(max_calls=5, window=30)
async def cmd_playlist(client: Client, message: Message):
    """Route /playlist sub-commands."""
    user = message.from_user
    lang = await get_user_lang(user.id)
    chat_id = message.chat.id

    parts = message.text.split(None, 2)
    # parts[0] = "/playlist", parts[1] = action, parts[2] = name (optional)

    if len(parts) < 2:
        await message.reply_text(_HELP_TEXT, quote=True)
        return

    action = parts[1].strip().lower()
    name = parts[2].strip() if len(parts) > 2 else None

    if action == "list":
        await _playlist_list(message, user.id, lang)

    elif action == "save":
        if not name:
            await message.reply_text(
                "❌ Usage: `/playlist save <name>`", quote=True
            )
            return
        await _playlist_save(message, user.id, chat_id, name, lang)

    elif action == "load":
        if not name:
            await message.reply_text(
                "❌ Usage: `/playlist load <name>`", quote=True
            )
            return
        await _playlist_load(message, user.id, chat_id, name, lang)

    elif action == "show":
        if not name:
            await message.reply_text(
                "❌ Usage: `/playlist show <name>`", quote=True
            )
            return
        await _playlist_show(message, user.id, name, lang)

    elif action == "delete":
        if not name:
            await message.reply_text(
                "❌ Usage: `/playlist delete <name>`", quote=True
            )
            return
        await _playlist_delete(message, user.id, name, lang)

    else:
        await message.reply_text(_HELP_TEXT, quote=True)


# ── Sub-command implementations ───────────────────────────────────────────────

async def _playlist_list(message: Message, user_id: int, lang: str) -> None:
    """List all saved playlists for the user."""
    names = await list_playlists(user_id)
    if not names:
        await message.reply_text(get_text("no_playlists", lang=lang), quote=True)
        return
    playlist_lines = "\n".join(f"• `{name}`" for name in names)
    await message.reply_text(
        get_text("playlist_list", lang=lang, list=playlist_lines),
        quote=True,
    )


async def _playlist_save(
    message: Message, user_id: int, chat_id: int, name: str, lang: str
) -> None:
    """Save the current queue as a named playlist."""
    if len(name) > 50:
        await message.reply_text("❌ Playlist name must be ≤ 50 characters.", quote=True)
        return

    tracks = await queue_manager.get_all(chat_id)
    np = await queue_manager.get_current(chat_id)

    # Include the now-playing track at the front so it's preserved
    all_tracks = []
    if np:
        all_tracks.append(np)
    all_tracks.extend(tracks)

    if not all_tracks:
        await message.reply_text(
            "❌ The queue is empty. Add some tracks before saving a playlist.",
            quote=True,
        )
        return

    # Limit to MAX_PLAYLIST_SIZE
    all_tracks = all_tracks[: config.MAX_PLAYLIST_SIZE]

    # Strip stream URLs before saving (they expire; will be re-resolved on load)
    saveable = []
    for t in all_tracks:
        entry = {k: v for k, v in t.items() if k != "stream_url"}
        saveable.append(entry)

    await save_playlist(user_id, name, saveable)
    await message.reply_text(
        get_text("playlist_saved", lang=lang, name=name, count=len(saveable)),
        quote=True,
    )


async def _playlist_load(
    message: Message, user_id: int, chat_id: int, name: str, lang: str
) -> None:
    """Load a saved playlist into the current queue."""
    pl = await get_playlist(user_id, name)
    if not pl:
        await message.reply_text(
            get_text("playlist_not_found", lang=lang, name=name), quote=True
        )
        return

    tracks = pl.get("tracks", [])
    if not tracks:
        await message.reply_text(
            f"❌ Playlist **{name}** is empty.", quote=True
        )
        return

    # Stamp requester info
    for t in tracks:
        t["requested_by"] = message.from_user.mention
        t["requested_by_id"] = message.from_user.id

    is_active = music_player.is_active(chat_id)
    if not is_active and tracks:
        first = tracks[0]
        rest = tracks[1:]
        try:
            await music_player.play(chat_id, first)
        except Exception as e:
            log.error(f"[{chat_id}] Playlist load play error: {e}")
            await message.reply_text(get_text("error_generic", lang=lang), quote=True)
            return
        if rest:
            await queue_manager.add_many(chat_id, rest)
    else:
        await queue_manager.add_many(chat_id, tracks)

    await message.reply_text(
        get_text("playlist_loaded", lang=lang, name=name, count=len(tracks)),
        quote=True,
    )


async def _playlist_show(
    message: Message, user_id: int, name: str, lang: str
) -> None:
    """Display the tracks stored inside a named playlist."""
    pl = await get_playlist(user_id, name)
    if not pl:
        await message.reply_text(
            get_text("playlist_not_found", lang=lang, name=name), quote=True
        )
        return

    tracks = pl.get("tracks", [])
    if not tracks:
        await message.reply_text(f"📭 Playlist **{name}** is empty.", quote=True)
        return

    lines = []
    for i, t in enumerate(tracks, start=1):
        title = truncate(t.get("title", "Unknown"), 45)
        duration = format_duration(t.get("duration", 0))
        source = t.get("source", "yt").upper()
        lines.append(f"`{i:>2}.` **{title}** [{duration}] — _{source}_")

    text = f"💾 **Playlist: {name}**\n({len(tracks)} tracks)\n\n" + "\n".join(lines)

    # Split if too long
    if len(text) > 4096:
        text = text[:4090] + "\n…"

    await message.reply_text(text, quote=True)


async def _playlist_delete(
    message: Message, user_id: int, name: str, lang: str
) -> None:
    """Permanently delete a saved playlist."""
    deleted = await delete_playlist(user_id, name)
    if deleted:
        await message.reply_text(
            f"🗑 Playlist **{name}** deleted.", quote=True
        )
    else:
        await message.reply_text(
            get_text("playlist_not_found", lang=lang, name=name), quote=True
        )
