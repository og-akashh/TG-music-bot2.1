"""
handlers/queue_handler.py — Queue inspection and manipulation commands.

Commands:
  /queue              — list all tracks currently in the queue
  /shuffle            — shuffle the queue
  /clearqueue         — remove all tracks from the queue
  /remove <position>  — remove a specific track by 1-based position
"""

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database import get_user_lang
from bot.locales.i18n import get_text
from bot.player.queue_manager import queue_manager
from bot.utils.decorators import admin_only, error_handler, group_only
from bot.utils.formatters import build_queue_text, format_duration
from bot.utils.logger import get_logger

log = get_logger(__name__)

_PAGE_SIZE = 10   # tracks shown per page


# ─── /queue ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("queue") & filters.group)
@error_handler
@group_only
async def cmd_queue(client: Client, message: Message):
    """
    Display the current queue with pagination (10 tracks per page).

    Usage: /queue [page]
    """
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    tracks = await queue_manager.get_all(chat_id)
    np = await queue_manager.get_current(chat_id)

    if not tracks and not np:
        await message.reply_text(get_text("queue_empty", lang=lang), quote=True)
        return

    # Parse page number from command args
    parts = message.text.split()
    try:
        page = max(1, int(parts[1])) if len(parts) > 1 else 1
    except ValueError:
        page = 1

    total_pages = max(1, (len(tracks) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * _PAGE_SIZE
    page_tracks = tracks[offset: offset + _PAGE_SIZE]

    # Build text
    header = ""
    if np:
        header = (
            f"▶️ **Now Playing:**\n"
            f"   {np.get('title', 'Unknown')} "
            f"[{format_duration(np.get('duration', 0))}]\n\n"
        )

    queue_text = build_queue_text(page_tracks, offset=offset)
    footer = f"\n\nPage {page}/{total_pages}  •  {len(tracks)} track(s) in queue"

    text = header + get_text("queue_header", lang=lang, count=len(tracks)) + queue_text + footer

    # Pagination buttons
    buttons = []
    if total_pages > 1:
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

    kb = InlineKeyboardMarkup(buttons) if buttons else None
    await message.reply_text(text, reply_markup=kb, quote=True)


# ─── /shuffle ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("shuffle") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_shuffle(client: Client, message: Message):
    """Randomly shuffle all tracks in the queue."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    length = await queue_manager.length(chat_id)
    if length == 0:
        await message.reply_text(get_text("queue_empty", lang=lang), quote=True)
        return

    await queue_manager.shuffle(chat_id)
    await message.reply_text(
        f"{get_text('queue_shuffled', lang=lang)} ({length} tracks)",
        quote=True,
    )


# ─── /clearqueue ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("clearqueue") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_clearqueue(client: Client, message: Message):
    """Clear all tracks from the queue (does not stop current playback)."""
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    from bot.database import queue_clear
    await queue_clear(chat_id)   # Clear queue only, don't touch now-playing
    await message.reply_text(get_text("queue_cleared", lang=lang), quote=True)


# ─── /remove ─────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("remove") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_remove(client: Client, message: Message):
    """
    Remove a specific track from the queue by its 1-based position.

    Usage: /remove <position>
    """
    chat_id = message.chat.id
    lang = await get_user_lang(message.from_user.id)

    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "❌ Usage: `/remove <position>`\n\nExample: `/remove 3`",
            quote=True,
        )
        return

    try:
        position = int(parts[1].strip())
    except ValueError:
        await message.reply_text("❌ Position must be a number.", quote=True)
        return

    if position < 1:
        await message.reply_text("❌ Position must be 1 or greater.", quote=True)
        return

    # Peek at the track before removing so we can confirm to the user
    tracks = await queue_manager.get_all(chat_id)
    if position > len(tracks):
        await message.reply_text(
            f"❌ Position {position} is out of range. Queue has {len(tracks)} track(s).",
            quote=True,
        )
        return

    track_to_remove = tracks[position - 1]
    success = await queue_manager.remove(chat_id, position)

    if success:
        await message.reply_text(
            f"🗑 Removed **{track_to_remove.get('title', 'Unknown')}** "
            f"from position {position}.",
            quote=True,
        )
    else:
        await message.reply_text(
            f"❌ Could not remove track at position {position}.",
            quote=True,
        )
