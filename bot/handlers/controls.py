"""
handlers/controls.py — Playback control commands.

Commands handled:
  /pause   — pause the current stream
  /resume  — resume a paused stream
  /skip    — skip to next track in queue
  /stop    — stop all playback and clear queue
  /seek    — seek to a specific time position
  /volume  — get or set the playback volume
  /loop    — cycle loop mode (off → single → queue → off)
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.database import get_user_lang, get_volume, get_loop
from bot.locales.i18n import get_text
from bot.player.music_player import music_player
from bot.player.queue_manager import queue_manager
from bot.utils.decorators import admin_only, error_handler, group_only, rate_limit
from bot.utils.formatters import format_duration, parse_time_to_seconds
from bot.utils.logger import get_logger

log = get_logger(__name__)


# ─── /pause ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("pause") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_pause(client: Client, message: Message):
    """Pause the active stream. Only group admins may call this."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    if not music_player.is_active(chat_id):
        await message.reply_text(get_text("no_active_stream", lang=lang), quote=True)
        return

    success = await music_player.pause(chat_id)
    if success:
        await message.reply_text(get_text("paused", lang=lang), quote=True)
    else:
        await message.reply_text("⚠️ Already paused or no active stream.", quote=True)


# ─── /resume ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("resume") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_resume(client: Client, message: Message):
    """Resume a paused stream. Only group admins may call this."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    if not music_player.is_paused(chat_id):
        await message.reply_text("⚠️ Nothing is paused right now.", quote=True)
        return

    success = await music_player.resume(chat_id)
    if success:
        await message.reply_text(get_text("resumed", lang=lang), quote=True)
    else:
        await message.reply_text(get_text("no_active_stream", lang=lang), quote=True)


# ─── /skip ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("skip") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_skip(client: Client, message: Message):
    """Skip the current track and start playing the next one in queue."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    if not music_player.is_active(chat_id):
        await message.reply_text(get_text("no_active_stream", lang=lang), quote=True)
        return

    next_track = await music_player.skip(chat_id)
    if next_track:
        await message.reply_text(
            f"{get_text('skipped', lang=lang)}\n▶️ **{next_track.get('title', 'Unknown')}**",
            quote=True,
        )
    else:
        await message.reply_text(
            f"{get_text('skipped', lang=lang)}\n{get_text('queue_finished', lang=lang)}",
            quote=True,
        )


# ─── /stop ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("stop") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_stop(client: Client, message: Message):
    """Stop all playback, clear the queue, and leave the voice chat."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    await music_player.stop(chat_id)
    await message.reply_text(get_text("stopped", lang=lang), quote=True)


# ─── /seek ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("seek") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_seek(client: Client, message: Message):
    """
    Seek to a position in the current track.

    Usage:
      /seek 90       → seek to 1 minute 30 seconds
      /seek 1:30     → same, in MM:SS format
      /seek 1:30:00  → HH:MM:SS format
    """
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    if not music_player.is_active(chat_id):
        await message.reply_text(get_text("no_active_stream", lang=lang), quote=True)
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "❌ Usage: `/seek <time>`\n\nExamples:\n`/seek 90`\n`/seek 1:30`",
            quote=True,
        )
        return

    seconds = parse_time_to_seconds(parts[1].strip())
    if seconds < 0:
        await message.reply_text(get_text("seek_invalid", lang=lang), quote=True)
        return

    # Validate against track duration
    np = await queue_manager.get_current(chat_id)
    if np and np.get("duration") and seconds > np["duration"]:
        await message.reply_text(
            f"❌ Seek position {format_duration(seconds)} exceeds track duration "
            f"{format_duration(np['duration'])}.",
            quote=True,
        )
        return

    await music_player.seek(chat_id, seconds)
    await message.reply_text(
        get_text("seek_success", lang=lang, position=format_duration(seconds)),
        quote=True,
    )


# ─── /volume ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("volume") & filters.group)
@error_handler
@group_only
@rate_limit(max_calls=5, window=15)
async def cmd_volume(client: Client, message: Message):
    """
    Get or set the playback volume.

    Usage:
      /volume        → show current volume
      /volume 80     → set volume to 80%
    """
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    parts = message.text.split(None, 1)

    if len(parts) < 2 or not parts[1].strip():
        # Show current volume
        current = await get_volume(chat_id)
        await message.reply_text(
            f"🔊 Current volume: **{current}%**\n\nUse `/volume <1-200>` to change it.",
            quote=True,
        )
        return

    try:
        vol = int(parts[1].strip())
    except ValueError:
        await message.reply_text(get_text("volume_invalid", lang=lang), quote=True)
        return

    if not 1 <= vol <= 200:
        await message.reply_text(get_text("volume_invalid", lang=lang), quote=True)
        return

    await music_player.set_volume(chat_id, vol)
    await message.reply_text(
        get_text("volume_set", lang=lang, volume=vol),
        quote=True,
    )


# ─── /loop ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("loop") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_loop(client: Client, message: Message):
    """Cycle the loop mode: off → single → queue → off."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    new_mode = await queue_manager.cycle_loop(chat_id)

    mode_text_key = {
        "off": "loop_off",
        "single": "loop_single",
        "queue": "loop_queue",
    }.get(new_mode, "loop_off")

    await message.reply_text(get_text(mode_text_key, lang=lang), quote=True)


# ─── /nowplaying ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["np", "nowplaying"]) & filters.group)
@error_handler
@group_only
async def cmd_now_playing(client: Client, message: Message):
    """Display info about the currently playing track."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    np = await queue_manager.get_current(chat_id)
    if not np:
        await message.reply_text(get_text("no_active_stream", lang=lang), quote=True)
        return

    volume = await get_volume(chat_id)
    loop_mode = await get_loop(chat_id)
    duration_str = format_duration(np.get("duration", 0))

    await message.reply_text(
        get_text(
            "now_playing",
            lang=lang,
            title=np.get("title", "Unknown"),
            duration=duration_str,
            user=np.get("requested_by", "Unknown"),
            volume=volume,
            loop=loop_mode.capitalize(),
        ),
        quote=True,
    )
