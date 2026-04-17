"""
handlers/lyrics_handler.py — /lyrics command.

Usage:
  /lyrics           → fetch lyrics for the currently playing track
  /lyrics <query>   → fetch lyrics for the given query

Long lyrics are split into multiple messages to stay within
Telegram's 4096-character message limit.
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.database import get_user_lang
from bot.locales.i18n import get_text
from bot.player.queue_manager import queue_manager
from bot.services.lyrics import chunk_lyrics, get_lyrics
from bot.utils.decorators import error_handler, group_only, rate_limit
from bot.utils.logger import get_logger

log = get_logger(__name__)


@Client.on_message(filters.command("lyrics"))
@error_handler
@rate_limit(max_calls=3, window=60)
async def cmd_lyrics(client: Client, message: Message):
    """
    Fetch and send lyrics for the current or a specified track.

    Works in both private chats and groups.
    """
    user = message.from_user
    chat_id = message.chat.id
    lang = await get_user_lang(user.id)

    parts = message.text.split(None, 1)
    query = parts[1].strip() if len(parts) > 1 else None

    title = ""
    artist = ""

    if not query:
        # Try to use the currently playing track
        np = await queue_manager.get_current(chat_id)
        if not np:
            await message.reply_text(
                "❌ No track is currently playing. "
                "Use `/lyrics <song name>` to search.",
                quote=True,
            )
            return
        title = np.get("title", "")
        artist = np.get("artist", "")
    else:
        # Allow "Artist - Title" format
        if " - " in query:
            parts_split = query.split(" - ", 1)
            artist = parts_split[0].strip()
            title = parts_split[1].strip()
        else:
            title = query

    if not title:
        await message.reply_text(
            "❌ Could not determine the track title. "
            "Try `/lyrics Artist - Song Title`.",
            quote=True,
        )
        return

    status_msg = await message.reply_text(
        f"🔍 Fetching lyrics for **{title}**{f' by {artist}' if artist else ''}…",
        quote=True,
    )

    lyrics = await get_lyrics(title, artist)

    if not lyrics:
        await status_msg.edit_text(
            get_text("lyrics_not_found", lang=lang, title=title)
        )
        return

    chunks = chunk_lyrics(lyrics, max_len=4000)

    # Send first chunk as edit of status message
    header = get_text("lyrics_found", lang=lang, title=title, lyrics="")
    first_chunk = f"{header}\n{chunks[0]}"

    # If only one chunk, edit the status message directly
    if len(chunks) == 1:
        await status_msg.edit_text(first_chunk[:4096])
        return

    # Multiple chunks: edit status → send remaining as follow-ups
    await status_msg.edit_text(
        f"📝 **Lyrics — {title}**\n_(Part 1/{len(chunks)})_\n\n{chunks[0]}"
    )
    for i, chunk in enumerate(chunks[1:], start=2):
        await message.reply_text(
            f"📝 **Lyrics — {title}**\n_(Part {i}/{len(chunks)})_\n\n{chunk}"
        )
