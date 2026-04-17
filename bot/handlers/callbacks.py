"""
handlers/callbacks.py — Inline keyboard callback query dispatcher.

Handles button presses on Now Playing cards and queue pagination.

Callback data patterns:
  pause_{chat_id}           — pause playback
  resume_{chat_id}          — resume playback
  skip_{chat_id}            — skip track
  stop_{chat_id}            — stop and clear queue
  prev_{chat_id}            — not implemented (placeholder)
  vol_down_{chat_id}        — decrease volume by 10
  vol_up_{chat_id}          — increase volume by 10
  loop_{chat_id}            — cycle loop mode
  queue_{chat_id}           — show queue inline
  shuffle_{chat_id}         — shuffle queue
  filter_{name}_{chat_id}   — apply audio filter
  queue_page_{chat_id}_{p}  — queue pagination
  noop                      — do nothing (label buttons)
"""

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from bot.database import get_user_lang, get_volume, set_volume
from bot.locales.i18n import get_text
from bot.player.audio_filters import FILTER_NAMES
from bot.player.music_player import music_player
from bot.player.queue_manager import queue_manager
from bot.utils.decorators import error_handler
from bot.utils.formatters import (
    build_queue_text,
    format_duration,
    now_playing_keyboard,
)
from bot.utils.logger import get_logger

log = get_logger(__name__)

_PAGE_SIZE = 10


# ─── Guard: only the user who requested or a group admin can press buttons ────

async def _is_allowed(client: Client, query: CallbackQuery, chat_id: int) -> bool:
    """
    Allow:
      - The user who requested the current track
      - Any Telegram group administrator
      - The bot owner
    """
    from bot.config import config
    if query.from_user.id == config.OWNER_ID:
        return True
    try:
        member = await client.get_chat_member(chat_id, query.from_user.id)
        return member.status.value in ("administrator", "creator")
    except Exception:
        return False


# ─── No-op (label button) ─────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^noop$"))
async def cb_noop(client: Client, query: CallbackQuery):
    await query.answer()


# ─── Pause ────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^pause_(-?\d+)$"))
@error_handler
async def cb_pause(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can control playback.", show_alert=True)
        return
    lang = await get_user_lang(query.from_user.id)
    success = await music_player.pause(chat_id)
    if success:
        # Update button to show Resume
        try:
            await query.message.edit_reply_markup(
                now_playing_keyboard(chat_id, is_paused=True)
            )
        except Exception:
            pass
        await query.answer(get_text("paused", lang=lang))
    else:
        await query.answer("⚠️ Nothing to pause.", show_alert=True)


# ─── Resume ───────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^resume_(-?\d+)$"))
@error_handler
async def cb_resume(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can control playback.", show_alert=True)
        return
    lang = await get_user_lang(query.from_user.id)
    success = await music_player.resume(chat_id)
    if success:
        try:
            await query.message.edit_reply_markup(
                now_playing_keyboard(chat_id, is_paused=False)
            )
        except Exception:
            pass
        await query.answer(get_text("resumed", lang=lang))
    else:
        await query.answer("⚠️ Nothing to resume.", show_alert=True)


# ─── Skip ─────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^skip_(-?\d+)$"))
@error_handler
async def cb_skip(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can control playback.", show_alert=True)
        return
    lang = await get_user_lang(query.from_user.id)
    if not music_player.is_active(chat_id):
        await query.answer(get_text("no_active_stream", lang=lang), show_alert=True)
        return
    next_track = await music_player.skip(chat_id)
    msg = get_text("skipped", lang=lang)
    if next_track:
        msg += f"\n▶️ {next_track.get('title', 'Unknown')}"
    await query.answer(msg[:200])


# ─── Stop ─────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^stop_(-?\d+)$"))
@error_handler
async def cb_stop(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can control playback.", show_alert=True)
        return
    lang = await get_user_lang(query.from_user.id)
    await music_player.stop(chat_id)
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer(get_text("stopped", lang=lang))


# ─── Previous (placeholder — yt-dlp doesn't expose history per stream) ────────

@Client.on_callback_query(filters.regex(r"^prev_(-?\d+)$"))
@error_handler
async def cb_prev(client: Client, query: CallbackQuery):
    await query.answer("⏮ Previous track is not available in streaming mode.", show_alert=True)


# ─── Volume down ──────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^vol_down_(-?\d+)$"))
@error_handler
async def cb_vol_down(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can change volume.", show_alert=True)
        return
    current = await get_volume(chat_id)
    new_vol = max(10, current - 10)
    await music_player.set_volume(chat_id, new_vol)
    await query.answer(f"🔉 Volume: {new_vol}%")


# ─── Volume up ────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^vol_up_(-?\d+)$"))
@error_handler
async def cb_vol_up(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can change volume.", show_alert=True)
        return
    current = await get_volume(chat_id)
    new_vol = min(200, current + 10)
    await music_player.set_volume(chat_id, new_vol)
    await query.answer(f"🔊 Volume: {new_vol}%")


# ─── Loop ─────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^loop_(-?\d+)$"))
@error_handler
async def cb_loop(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can change loop mode.", show_alert=True)
        return
    lang = await get_user_lang(query.from_user.id)
    new_mode = await queue_manager.cycle_loop(chat_id)
    mode_labels = {"off": "🔁 Off", "single": "🔂 Single", "queue": "🔁 Queue"}
    await query.answer(f"Loop: {mode_labels.get(new_mode, new_mode)}")


# ─── Queue (inline display) ───────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^queue_(-?\d+)$"))
@error_handler
async def cb_queue(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    tracks = await queue_manager.get_all(chat_id)
    np = await queue_manager.get_current(chat_id)

    if not tracks and not np:
        await query.answer("📭 Queue is empty.", show_alert=True)
        return

    header = ""
    if np:
        header = f"▶️ **{np.get('title', 'Unknown')}** [{format_duration(np.get('duration', 0))}]\n\n"

    page_tracks = tracks[:_PAGE_SIZE]
    body = build_queue_text(page_tracks, offset=0)
    more = f"\n…and {len(tracks) - _PAGE_SIZE} more" if len(tracks) > _PAGE_SIZE else ""

    await query.answer()
    try:
        await query.message.reply_text(
            f"📋 **Queue ({len(tracks)} track(s))**\n\n{header}{body}{more}"
        )
    except Exception as e:
        log.warning(f"Queue CB reply error: {e}")


# ─── Shuffle ──────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^shuffle_(-?\d+)$"))
@error_handler
async def cb_shuffle(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can shuffle.", show_alert=True)
        return
    length = await queue_manager.length(chat_id)
    if length == 0:
        await query.answer("📭 Queue is empty.", show_alert=True)
        return
    await queue_manager.shuffle(chat_id)
    await query.answer(f"🔀 Queue shuffled! ({length} tracks)")


# ─── Audio filter ────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^filter_(\w+)_(-?\d+)$"))
@error_handler
async def cb_filter(client: Client, query: CallbackQuery):
    filter_name = query.matches[0].group(1)
    chat_id = int(query.matches[0].group(2))
    if not await _is_allowed(client, query, chat_id):
        await query.answer("🔐 Only admins can change filters.", show_alert=True)
        return
    if not music_player.is_active(chat_id):
        await query.answer("❌ No active stream.", show_alert=True)
        return
    await music_player.apply_filter(chat_id, filter_name)
    label = FILTER_NAMES.get(filter_name, filter_name)
    if filter_name == "none":
        await query.answer("🎚 Filter removed.")
    else:
        await query.answer(f"🎚 Filter: {label}")


# ─── Queue pagination ─────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^queue_page_(-?\d+)_(\d+)$"))
@error_handler
async def cb_queue_page(client: Client, query: CallbackQuery):
    chat_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))

    tracks = await queue_manager.get_all(chat_id)
    np = await queue_manager.get_current(chat_id)

    total_pages = max(1, (len(tracks) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * _PAGE_SIZE
    page_tracks = tracks[offset: offset + _PAGE_SIZE]

    header = ""
    if np and page == 1:
        header = (
            f"▶️ **Now Playing:**\n"
            f"   {np.get('title', 'Unknown')} "
            f"[{format_duration(np.get('duration', 0))}]\n\n"
        )

    body = build_queue_text(page_tracks, offset=offset)
    footer = f"\n\nPage {page}/{total_pages}  •  {len(tracks)} track(s)"

    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    row = []
    if page > 1:
        row.append(
            InlineKeyboardButton(
                "◀️ Prev", callback_data=f"queue_page_{chat_id}_{page - 1}"
            )
        )
    row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        row.append(
            InlineKeyboardButton(
                "Next ▶️", callback_data=f"queue_page_{chat_id}_{page + 1}"
            )
        )
    buttons.append(row)

    try:
        await query.message.edit_text(
            f"📋 **Queue ({len(tracks)} tracks)**\n\n{header}{body}{footer}",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception:
        pass
    await query.answer()
