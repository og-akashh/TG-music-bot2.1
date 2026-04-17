"""
main.py — Music Bot entry point.

Boot sequence
─────────────
1.  Validate environment variables
2.  Connect to Redis
3.  Connect to MongoDB
4.  Create Pyrogram bot client  (receives commands)
5.  Create Pyrogram userbot client  (joins voice chats)
6.  Create PyTgCalls instance  (manages audio streams)
7.  Register all Pyrogram handlers  (importing handlers package)
8.  Wire MusicPlayer singleton with clients
9.  Start background maintenance tasks
10. Run until SIGINT / SIGTERM
11. Graceful shutdown: stop streams, disconnect DBs
"""

import asyncio
import signal
import sys

from pyrogram import Client, idle
from pytgcalls import PyTgCalls

from bot.config import config
from bot.database import mongo_connect, mongo_disconnect, redis_connect, redis_disconnect
from bot.player.music_player import music_player
from bot.utils.cache_manager import maintain_cache
from bot.utils.logger import LOGGER

# ── Import handlers so their decorators fire ──────────────────────────────────
# This must happen AFTER the client is created so Pyrogram can receive them.
# We import inside _start() to ensure the Client class is already patched.


async def _background_cache_maintenance() -> None:
    """Periodically evict stale audio files to respect MAX_CACHE_SIZE_MB."""
    while True:
        try:
            await maintain_cache()
        except Exception as e:
            LOGGER.warning(f"Cache maintenance error: {e}")
        await asyncio.sleep(3600)   # run every hour


async def _start() -> None:
    # ── 1. Validate config ────────────────────────────────────────────────
    config.validate()
    LOGGER.info("Configuration validated ✓")

    # ── 2. Connect databases ──────────────────────────────────────────────
    await redis_connect()
    await mongo_connect()

    # ── 3. Pyrogram bot client ────────────────────────────────────────────
    bot = Client(
        name="music_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        # In-memory session for the bot account
        in_memory=True,
    )

    # ── 4. Pyrogram userbot client (needs a session string) ───────────────
    userbot = Client(
        name="music_userbot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.SESSION_STRING,
        in_memory=True,
    )

    # ── 5. PyTgCalls — attach to the USERBOT ─────────────────────────────
    pytgcalls = PyTgCalls(userbot)

    # ── 6. Register handlers (decorators run at import time) ──────────────
    # Import AFTER creating clients so Pyrogram's monkey-patched Client
    # class already exists and can accept @Client.on_message registrations.
    import bot.handlers  # noqa: F401 — side-effect import

    # ── 7. Wire MusicPlayer ───────────────────────────────────────────────
    music_player.setup(bot=bot, userbot=userbot, pytgcalls=pytgcalls)

    # ── 8. Start clients ──────────────────────────────────────────────────
    await bot.start()
    await userbot.start()
    await pytgcalls.start()

    bot_info = await bot.get_me()
    LOGGER.info(
        f"Bot started as @{bot_info.username} "
        f"(id={bot_info.id}) | API_ID={config.API_ID}"
    )

    # ── 9. Optional web dashboard ─────────────────────────────────────────
    if config.DASHBOARD_ENABLED:
        try:
            from dashboard.app import start_dashboard
            asyncio.create_task(start_dashboard())
            LOGGER.info(f"Dashboard starting on port {config.DASHBOARD_PORT}")
        except ImportError:
            LOGGER.warning("Dashboard dependencies not installed. Skipping dashboard.")

    # ── 10. Background tasks ──────────────────────────────────────────────
    asyncio.create_task(_background_cache_maintenance())
    LOGGER.info("Background cache maintenance task started ✓")

    # Notify log channel if configured
    if config.LOG_CHANNEL:
        try:
            await bot.send_message(
                config.LOG_CHANNEL,
                f"🟢 **{config.BOT_NAME} started**\n"
                f"Running as @{bot_info.username}",
            )
        except Exception as e:
            LOGGER.warning(f"Could not send startup message to log channel: {e}")

    LOGGER.info("✅ Bot is fully running. Press Ctrl+C to stop.")

    # ── 11. Idle until SIGINT / SIGTERM ───────────────────────────────────
    await idle()

    # ── 12. Graceful shutdown ─────────────────────────────────────────────
    LOGGER.info("Shutting down…")

    if config.LOG_CHANNEL:
        try:
            await bot.send_message(config.LOG_CHANNEL, f"🔴 **{config.BOT_NAME} stopped**")
        except Exception:
            pass

    await pytgcalls.stop()
    await userbot.stop()
    await bot.stop()
    await mongo_disconnect()
    await redis_disconnect()

    LOGGER.info("Shutdown complete. Goodbye! 👋")


def _handle_signal(sig, frame) -> None:
    LOGGER.info(f"Received signal {sig}. Initiating graceful shutdown…")
    sys.exit(0)


if __name__ == "__main__":
    # Register OS-level signal handlers for clean container shutdowns
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        asyncio.run(_start())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Bot stopped by user.")
    except Exception as exc:
        LOGGER.exception(f"Fatal error: {exc}")
        sys.exit(1)
