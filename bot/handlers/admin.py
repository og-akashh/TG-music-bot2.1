"""
handlers/admin.py — Owner / global-admin commands.

All commands here require either bot-owner status (OWNER_ID)
or Telegram group admin.

Commands:
  /adminadd   <user_id>   — grant bot-admin to a user in this chat
  /adminremove <user_id>  — revoke bot-admin from a user
  /broadcast  <text>      — send a message to all registered chats (owner only)
  /stats                  — show global bot statistics (owner only)
  /clearcache             — evict disk audio cache (owner only)
  /leave      <chat_id>   — force-leave a group (owner only)
"""

from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import config
from bot.database import (
    add_chat_admin,
    get_stats,
    get_user_lang,
    mongo_connect,
    remove_chat_admin,
)
from bot.utils.cache_manager import clear_cache, get_cache_stats
from bot.utils.decorators import admin_only, error_handler, group_only, owner_only
from bot.utils.logger import get_logger

log = get_logger(__name__)


# ─── /adminadd ────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("adminadd") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_admin_add(client: Client, message: Message):
    """
    /adminadd <user_id | @username | reply>

    Grant the specified user bot-admin privileges in this chat.
    The user still needs to be a real Telegram group admin to pass
    the Telegram-level admin check for restricted commands.
    """
    chat_id = message.chat.id
    target_user = None

    # If this is a reply, use the replied-to user
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text(
                "❌ Usage: `/adminadd <user_id>` or reply to a user.", quote=True
            )
            return
        try:
            uid = int(parts[1].lstrip("@"))
        except ValueError:
            try:
                user = await client.get_users(parts[1])
                uid = user.id
            except Exception:
                await message.reply_text("❌ User not found.", quote=True)
                return
        uid = uid   # noqa

    user_id = target_user.id if target_user else uid
    await add_chat_admin(chat_id, user_id)
    await message.reply_text(
        f"✅ User `{user_id}` is now a bot admin in this chat.", quote=True
    )


# ─── /adminremove ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("adminremove") & filters.group)
@error_handler
@group_only
@admin_only
async def cmd_admin_remove(client: Client, message: Message):
    """
    /adminremove <user_id | @username | reply>

    Revoke bot-admin privileges for the specified user in this chat.
    """
    chat_id = message.chat.id
    target_id = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    else:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text(
                "❌ Usage: `/adminremove <user_id>` or reply to a user.", quote=True
            )
            return
        try:
            target_id = int(parts[1].lstrip("@"))
        except ValueError:
            try:
                user = await client.get_users(parts[1])
                target_id = user.id
            except Exception:
                await message.reply_text("❌ User not found.", quote=True)
                return

    await remove_chat_admin(chat_id, target_id)
    await message.reply_text(
        f"✅ Bot-admin revoked from user `{target_id}` in this chat.", quote=True
    )


# ─── /stats ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("stats"))
@error_handler
@owner_only
async def cmd_stats(client: Client, message: Message):
    """Show global database and cache statistics."""
    db_stats = await get_stats()
    cache_info = await get_cache_stats()

    text = (
        "📊 **Bot Statistics**\n\n"
        "**Database:**\n"
        f"  👤 Users:        `{db_stats.get('users', 0)}`\n"
        f"  💬 Chats:        `{db_stats.get('chats', 0)}`\n"
        f"  💾 Playlists:    `{db_stats.get('playlists', 0)}`\n"
        f"  📜 History rows: `{db_stats.get('history_entries', 0)}`\n\n"
        "**Cache (disk):**\n"
        f"  📁 Files:  `{cache_info.get('file_count', 0)}`\n"
        f"  💿 Size:   `{cache_info.get('total_mb', 0)} MB` / "
        f"`{cache_info.get('max_mb', 0)} MB`\n"
        f"  📈 Usage:  `{cache_info.get('usage_percent', 0)}%`\n"
    )
    await message.reply_text(text, quote=True)


# ─── /clearcache ─────────────────────────────────────────────────────────────

@Client.on_message(filters.command("clearcache"))
@error_handler
@owner_only
async def cmd_clearcache(client: Client, message: Message):
    """Delete all cached audio files from disk."""
    msg = await message.reply_text("⏳ Clearing audio cache…", quote=True)
    count = await clear_cache()
    await msg.edit_text(f"✅ Cache cleared — **{count}** file(s) deleted.")


# ─── /broadcast ──────────────────────────────────────────────────────────────

@Client.on_message(filters.command("broadcast") & filters.private)
@error_handler
@owner_only
async def cmd_broadcast(client: Client, message: Message):
    """
    /broadcast <text>

    Sends a message to every chat recorded in the database.
    Runs as a background task so as not to block the event loop.
    """
    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "❌ Usage: `/broadcast <message text>`", quote=True
        )
        return

    broadcast_text = parts[1].strip()

    # Collect all chat IDs from MongoDB
    import motor.motor_asyncio
    from bot.database.mongo import _col

    cursor = _col("chats").find({}, {"chat_id": 1})
    chat_ids = [doc["chat_id"] async for doc in cursor]

    status_msg = await message.reply_text(
        f"📣 Broadcasting to **{len(chat_ids)}** chats…", quote=True
    )

    sent = 0
    failed = 0
    for cid in chat_ids:
        try:
            await client.send_message(cid, f"📢 **Announcement**\n\n{broadcast_text}")
            sent += 1
        except Exception as e:
            log.warning(f"Broadcast failed for {cid}: {e}")
            failed += 1

    await status_msg.edit_text(
        f"✅ Broadcast complete.\n\n"
        f"  ✔️ Sent:   {sent}\n"
        f"  ❌ Failed: {failed}"
    )


# ─── /leave ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("leave") & filters.private)
@error_handler
@owner_only
async def cmd_leave(client: Client, message: Message):
    """
    /leave <chat_id>

    Force the bot to leave a specific group.
    """
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("❌ Usage: `/leave <chat_id>`", quote=True)
        return
    try:
        target_chat = int(parts[1])
    except ValueError:
        await message.reply_text("❌ chat_id must be a number.", quote=True)
        return
    try:
        await client.leave_chat(target_chat)
        await message.reply_text(f"✅ Left chat `{target_chat}`.", quote=True)
    except Exception as e:
        await message.reply_text(f"❌ Failed: {e}", quote=True)
