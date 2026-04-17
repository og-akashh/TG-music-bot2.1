"""
handlers/start.py — /start, /help, /ping commands.
"""

import time

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import config
from bot.database import upsert_user, get_user_lang
from bot.locales.i18n import get_text
from bot.utils.decorators import error_handler, get_uptime
from bot.utils.logger import get_logger

log = get_logger(__name__)

# ── /start ────────────────────────────────────────────────────────────────────


@Client.on_message(filters.command("start") & filters.private)
@error_handler
async def cmd_start_private(client: Client, message: Message):
    """Welcome message in private chat. Registers the user in MongoDB."""
    user = message.from_user
    lang = user.language_code or config.DEFAULT_LANG

    # Register / update user record
    await upsert_user(
        user.id,
        {
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "",
            "lang": lang,
        },
    )

    text = get_text(
        "start_message",
        lang=lang,
        name=user.mention,
        bot_name=config.BOT_NAME,
    )
    await message.reply_text(text, disable_web_page_preview=True)


@Client.on_message(filters.command("start") & filters.group)
@error_handler
async def cmd_start_group(client: Client, message: Message):
    """Minimal start response inside groups."""
    lang = await get_user_lang(message.from_user.id)
    await message.reply_text(
        f"👋 Hi! I'm **{config.BOT_NAME}**. Use /help to see available commands."
    )


# ── /help ─────────────────────────────────────────────────────────────────────


@Client.on_message(filters.command("help"))
@error_handler
async def cmd_help(client: Client, message: Message):
    """Send the full help text."""
    lang = await get_user_lang(message.from_user.id)
    await message.reply_text(
        get_text("help_message", lang=lang),
        disable_web_page_preview=True,
    )


# ── /ping ─────────────────────────────────────────────────────────────────────


@Client.on_message(filters.command("ping"))
@error_handler
async def cmd_ping(client: Client, message: Message):
    """Measure round-trip latency and report bot uptime."""
    lang = await get_user_lang(message.from_user.id)
    start = time.monotonic()
    sent = await message.reply_text("🏓 Pinging...")
    latency_ms = round((time.monotonic() - start) * 1000)

    await sent.edit_text(
        get_text(
            "ping_response",
            lang=lang,
            latency=latency_ms,
            uptime=get_uptime(),
        )
    )
