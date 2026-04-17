"""
queue_manager.py — High-level queue operations.

Wraps raw Redis primitives with validation, loop handling,
history tracking, and auto-play resolution.
"""

from typing import List, Optional

from bot.config import config
from bot.database import (
    queue_push, queue_pop, queue_peek, queue_get_all,
    queue_clear, queue_length, queue_remove_index, queue_shuffle,
    set_now_playing, get_now_playing, clear_now_playing,
    get_loop, set_loop, add_history,
)
from bot.services import youtube as yt
from bot.utils.logger import get_logger

log = get_logger(__name__)


class QueueManager:
    """Per-bot singleton; use .get(chat_id) for chat-specific operations."""

    # ── Add to queue ──────────────────────────────────────────────────────

    async def add(self, chat_id: int, track: dict) -> int:
        """Append a track. Returns new queue length."""
        if await queue_length(chat_id) >= config.MAX_QUEUE_SIZE:
            raise ValueError(f"Queue is full (max {config.MAX_QUEUE_SIZE} tracks).")
        length = await queue_push(chat_id, track)
        log.debug(f"[{chat_id}] Queued '{track.get('title')}' (pos {length})")
        return length

    async def add_many(self, chat_id: int, tracks: List[dict]) -> int:
        """Bulk-add up to MAX_QUEUE_SIZE tracks. Returns count added."""
        current = await queue_length(chat_id)
        slots = config.MAX_QUEUE_SIZE - current
        added = 0
        for track in tracks[:slots]:
            await queue_push(chat_id, track)
            added += 1
        return added

    # ── Dequeue ───────────────────────────────────────────────────────────

    async def next(self, chat_id: int) -> Optional[dict]:
        """
        Pop and return the next track, respecting loop mode.

        Loop modes:
          off    → pop from front
          single → re-enqueue at front (simulate by peeking + not popping)
          queue  → pop from front, push to back
        """
        loop_mode = await get_loop(chat_id)

        np = await get_now_playing(chat_id)

        if loop_mode == "single" and np:
            # Return same track again without touching queue
            return np

        track = await queue_pop(chat_id)

        if loop_mode == "queue" and track:
            # Push consumed track to back
            await queue_push(chat_id, track)

        return track

    async def peek_next(self, chat_id: int) -> Optional[dict]:
        return await queue_peek(chat_id)

    # ── Inspection ────────────────────────────────────────────────────────

    async def get_all(self, chat_id: int) -> List[dict]:
        return await queue_get_all(chat_id)

    async def length(self, chat_id: int) -> int:
        return await queue_length(chat_id)

    # ── Manipulation ──────────────────────────────────────────────────────

    async def clear(self, chat_id: int) -> None:
        await queue_clear(chat_id)
        await clear_now_playing(chat_id)

    async def shuffle(self, chat_id: int) -> None:
        await queue_shuffle(chat_id)

    async def remove(self, chat_id: int, index: int) -> bool:
        """Remove track at 1-based position. Returns success."""
        return await queue_remove_index(chat_id, index - 1)   # convert to 0-based

    # ── Loop mode ─────────────────────────────────────────────────────────

    async def cycle_loop(self, chat_id: int) -> str:
        """Cycle through off → single → queue → off. Returns new mode."""
        modes = ["off", "single", "queue"]
        current = await get_loop(chat_id)
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        await set_loop(chat_id, next_mode)
        return next_mode

    # ── Now playing ───────────────────────────────────────────────────────

    async def set_current(self, chat_id: int, track: dict) -> None:
        await set_now_playing(chat_id, track)
        await add_history(chat_id, track)

    async def get_current(self, chat_id: int) -> Optional[dict]:
        return await get_now_playing(chat_id)

    async def clear_current(self, chat_id: int) -> None:
        await clear_now_playing(chat_id)

    # ── Auto-play ─────────────────────────────────────────────────────────

    async def fetch_autoplay_tracks(self, chat_id: int) -> List[dict]:
        """Fetch related tracks when queue is empty and auto-play is on."""
        if not config.AUTO_PLAY:
            return []
        np = await get_now_playing(chat_id)
        if not np or not np.get("id"):
            return []
        try:
            related = await yt.get_related(np["id"], count=5)
            return related
        except Exception as e:
            log.warning(f"Auto-play fetch failed: {e}")
            return []


queue_manager = QueueManager()
