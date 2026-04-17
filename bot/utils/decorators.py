"""
decorators.py — Reusable command decorators.

• admin_only      — blocks non-admins
• owner_only      — blocks non-owners
• rate_limit      — per-user command throttling
• voice_chat_only — ensures a VC stream is active
• group_only      — ensures command runs in a group
"""

import functools
import time
from typing import Callable

from pyrogram import Client
from pyrogram.types import Message

from bot.config import config
from bot.database import get_user_role, rate_limit_check
from bot.locales.i18n import get_text
from bot.utils.logger import get_logger

log = get_logger(__name__)

_start_time = time.time()


def _get_lang(message: Message) -> str:
    return getattr(message.from_user, "language_code", "en") or "en"


def admin_only(func: Callable) -> Callable:
    """Allow only chat admins or bot owner."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        user_id = message.from_user.id
        chat_id = message.chat.id
        role = await get_user_role(user_id, chat_id)
        if role == "user":
            # Double-check via Telegram API (real-time admin status)
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status.value not in ("administrator", "creator"):
                    lang = _get_lang(message)
                    await message.reply_text(get_text("admin_only", lang))
                    return
            except Exception:
                lang = _get_lang(message)
                await message.reply_text(get_text("admin_only", lang))
                return
        return await func(client, message, *args, **kwargs)
    return wrapper


def owner_only(func: Callable) -> Callable:
    """Allow only the bot owner (OWNER_ID in config)."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.from_user.id != config.OWNER_ID:
            lang = _get_lang(message)
            await message.reply_text(get_text("owner_only", lang))
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def rate_limit(max_calls: int = 3, window: int = 30):
    """Throttle a command to max_calls per window (seconds) per user."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(client: Client, message: Message, *args, **kwargs):
            user_id = message.from_user.id
            command = func.__name__
            allowed = await rate_limit_check(user_id, command, max_calls, window)
            if not allowed:
                lang = _get_lang(message)
                await message.reply_text(get_text("rate_limited", lang))
                return
            return await func(client, message, *args, **kwargs)
        return wrapper
    return decorator


def group_only(func: Callable) -> Callable:
    """Ensures the command is used inside a group/supergroup."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        if message.chat.type.value not in ("group", "supergroup"):
            await message.reply_text("❌ This command only works in groups.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


def error_handler(func: Callable) -> Callable:
    """Catch all unhandled exceptions and reply with a friendly message."""
    @functools.wraps(func)
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            log.exception(f"Error in {func.__name__}: {e}")
            lang = _get_lang(message)
            await message.reply_text(get_text("error_generic", lang))
    return wrapper


def get_uptime() -> str:
    """Return human-readable bot uptime."""
    seconds = int(time.time() - _start_time)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"
