"""
music_player.py — Core voice-chat stream controller.

Responsibilities:
  • Join / leave voice chats
  • Start / pause / resume / stop streams
  • Seek within tracks
  • Volume control
  • Audio filter application
  • Auto-advance queue on stream end
  • Auto-reconnect on unexpected disconnect
  • Multi-chat isolation (state per chat_id)
"""

import asyncio
import traceback
from typing import Dict, Optional

from pyrogram import Client
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, AudioParameters
from pytgcalls.types.stream import StreamAudioEnded

from bot.config import config
from bot.database import get_volume, set_volume, get_chat_setting
from bot.player.audio_filters import build_ffmpeg_options
from bot.player.queue_manager import queue_manager
from bot.services import youtube as yt
from bot.utils.formatters import format_duration, now_playing_keyboard
from bot.utils.logger import get_logger
from bot.utils.thumbnail import generate_thumbnail

log = get_logger(__name__)


class PlayerState:
    """Mutable state for a single voice-chat session."""
    __slots__ = (
        "chat_id", "is_playing", "is_paused", "current_filter",
        "seek_pos", "np_message_id", "reconnect_attempts",
    )

    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.current_filter: str = "none"
        self.seek_pos: int = 0
        self.np_message_id: Optional[int] = None
        self.reconnect_attempts: int = 0


class MusicPlayer:
    """
    Singleton orchestrating all VC sessions.
    Initialised once in main.py and passed to handlers.
    """

    def __init__(self):
        self._states: Dict[int, PlayerState] = {}
        self._pytgcalls: Optional[PyTgCalls] = None
        self._bot: Optional[Client] = None
        self._userbot: Optional[Client] = None

    def setup(self, bot: Client, userbot: Client, pytgcalls: PyTgCalls) -> None:
        self._bot = bot
        self._userbot = userbot
        self._pytgcalls = pytgcalls
        self._register_callbacks()
        log.info("MusicPlayer initialised ✓")

    def _state(self, chat_id: int) -> PlayerState:
        if chat_id not in self._states:
            self._states[chat_id] = PlayerState(chat_id)
        return self._states[chat_id]

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _register_callbacks(self) -> None:
        @self._pytgcalls.on_stream_end()
        async def on_stream_end(_, update):
            if isinstance(update, StreamAudioEnded):
                await self._on_track_end(update.chat_id)

        @self._pytgcalls.on_closed_voice_chat()
        async def on_vc_closed(_, chat_id: int):
            log.warning(f"Voice chat closed in {chat_id}. Scheduling reconnect...")
            asyncio.create_task(self._reconnect(chat_id))

    async def _on_track_end(self, chat_id: int) -> None:
        state = self._state(chat_id)
        state.is_playing = False
        state.seek_pos = 0

        next_track = await queue_manager.next(chat_id)

        if not next_track and config.AUTO_PLAY:
            log.info(f"[{chat_id}] Queue empty — fetching auto-play tracks")
            related = await queue_manager.fetch_autoplay_tracks(chat_id)
            for t in related:
                await queue_manager.add(chat_id, t)
            next_track = await queue_manager.next(chat_id)

        if next_track:
            await self._play_track(chat_id, next_track)
        else:
            await queue_manager.clear_current(chat_id)
            log.info(f"[{chat_id}] Queue finished.")
            await self._send_to_chat(chat_id, "✅ Queue finished. No more tracks.")

    # ── Core playback ─────────────────────────────────────────────────────────

    async def play(self, chat_id: int, track: dict) -> None:
        """
        Start playing a track (or add to queue if something is already playing).
        """
        state = self._state(chat_id)

        if state.is_playing or state.is_paused:
            pos = await queue_manager.add(chat_id, track)
            return  # caller handles "added to queue" message

        # Ensure stream URL is fresh
        track = await self._ensure_stream_url(track)
        if not track:
            raise RuntimeError("Could not resolve stream URL.")

        await self._play_track(chat_id, track)

    async def _play_track(self, chat_id: int, track: dict) -> None:
        state = self._state(chat_id)

        # Resolve stream URL if missing
        track = await self._ensure_stream_url(track)
        if not track or not track.get("stream_url"):
            log.error(f"[{chat_id}] No stream URL for '{track}'")
            await self._on_track_end(chat_id)
            return

        volume = await get_volume(chat_id)
        ff_opts = build_ffmpeg_options(
            seek=0,
            filter_name=state.current_filter,
            volume=volume,
        )

        audio_stream = AudioPiped(
            track["stream_url"],
            audio_parameters=AudioParameters(
                bitrate=128,
            ),
            additional_ffmpeg_parameters=ff_opts.get("before_options", ""),
        )

        try:
            calls = await self._pytgcalls.get_active_call(chat_id)
            if calls:
                await self._pytgcalls.change_stream(chat_id, audio_stream)
            else:
                await self._pytgcalls.join_group_call(chat_id, audio_stream)

            state.is_playing = True
            state.is_paused = False
            state.reconnect_attempts = 0
            await queue_manager.set_current(chat_id, track)
            log.info(f"[{chat_id}] Now playing: {track.get('title')}")

            # Send Now Playing card
            asyncio.create_task(self._send_now_playing(chat_id, track))

        except Exception as e:
            log.error(f"[{chat_id}] Play error: {e}\n{traceback.format_exc()}")
            await self._on_track_end(chat_id)

    async def _ensure_stream_url(self, track: dict) -> Optional[dict]:
        """Re-fetch stream URL if missing or expired."""
        if track.get("stream_url"):
            return track
        url = track.get("webpage_url", "")
        if not url:
            return None
        fresh_url = await yt.resolve_stream_url(track)
        if fresh_url:
            track["stream_url"] = fresh_url
        return track if track.get("stream_url") else None

    # ── Controls ──────────────────────────────────────────────────────────────

    async def pause(self, chat_id: int) -> bool:
        state = self._state(chat_id)
        if not state.is_playing or state.is_paused:
            return False
        await self._pytgcalls.pause_stream(chat_id)
        state.is_paused = True
        state.is_playing = False
        return True

    async def resume(self, chat_id: int) -> bool:
        state = self._state(chat_id)
        if not state.is_paused:
            return False
        await self._pytgcalls.resume_stream(chat_id)
        state.is_playing = True
        state.is_paused = False
        return True

    async def skip(self, chat_id: int) -> Optional[dict]:
        next_track = await queue_manager.next(chat_id)
        if next_track:
            await self._play_track(chat_id, next_track)
        else:
            await self.stop(chat_id)
        return next_track

    async def stop(self, chat_id: int) -> None:
        state = self._state(chat_id)
        try:
            await self._pytgcalls.leave_group_call(chat_id)
        except Exception:
            pass
        state.is_playing = False
        state.is_paused = False
        await queue_manager.clear(chat_id)
        log.info(f"[{chat_id}] Stopped.")

    async def seek(self, chat_id: int, seconds: int) -> None:
        state = self._state(chat_id)
        np = await queue_manager.get_current(chat_id)
        if not np:
            return
        volume = await get_volume(chat_id)
        ff_opts = build_ffmpeg_options(
            seek=seconds,
            filter_name=state.current_filter,
            volume=volume,
        )
        audio_stream = AudioPiped(
            np["stream_url"],
            additional_ffmpeg_parameters=ff_opts.get("before_options", ""),
        )
        await self._pytgcalls.change_stream(chat_id, audio_stream)
        state.seek_pos = seconds

    async def set_volume(self, chat_id: int, volume: int) -> None:
        volume = max(1, min(200, volume))
        await set_volume(chat_id, volume)
        # Restart stream with new volume (pytgcalls doesn't support live volume via all backends)
        state = self._state(chat_id)
        np = await queue_manager.get_current(chat_id)
        if np and (state.is_playing or state.is_paused):
            ff_opts = build_ffmpeg_options(
                seek=state.seek_pos,
                filter_name=state.current_filter,
                volume=volume,
            )
            audio_stream = AudioPiped(
                np["stream_url"],
                additional_ffmpeg_parameters=ff_opts.get("before_options", ""),
            )
            await self._pytgcalls.change_stream(chat_id, audio_stream)

    async def apply_filter(self, chat_id: int, filter_name: str) -> None:
        state = self._state(chat_id)
        state.current_filter = filter_name
        np = await queue_manager.get_current(chat_id)
        volume = await get_volume(chat_id)
        if np and (state.is_playing or state.is_paused):
            ff_opts = build_ffmpeg_options(
                seek=state.seek_pos,
                filter_name=filter_name,
                volume=volume,
            )
            audio_stream = AudioPiped(
                np["stream_url"],
                additional_ffmpeg_parameters=ff_opts.get("before_options", ""),
            )
            await self._pytgcalls.change_stream(chat_id, audio_stream)

    # ── State queries ─────────────────────────────────────────────────────────

    def is_active(self, chat_id: int) -> bool:
        s = self._states.get(chat_id)
        return s is not None and (s.is_playing or s.is_paused)

    def is_paused(self, chat_id: int) -> bool:
        s = self._states.get(chat_id)
        return s is not None and s.is_paused

    # ── Auto-reconnect ────────────────────────────────────────────────────────

    async def _reconnect(self, chat_id: int) -> None:
        state = self._state(chat_id)
        MAX_RETRIES = 5
        if state.reconnect_attempts >= MAX_RETRIES:
            log.error(f"[{chat_id}] Max reconnect attempts reached. Giving up.")
            await queue_manager.clear(chat_id)
            return

        np = await queue_manager.get_current(chat_id)
        if not np:
            return

        state.reconnect_attempts += 1
        delay = 5 * state.reconnect_attempts
        log.info(f"[{chat_id}] Reconnecting in {delay}s (attempt {state.reconnect_attempts})...")
        await asyncio.sleep(delay)

        try:
            await self._play_track(chat_id, np)
            log.info(f"[{chat_id}] Reconnected successfully.")
        except Exception as e:
            log.error(f"[{chat_id}] Reconnect failed: {e}")
            await self._reconnect(chat_id)

    # ── Now Playing card ──────────────────────────────────────────────────────

    async def _send_now_playing(self, chat_id: int, track: dict) -> None:
        from bot.database import get_loop
        state = self._state(chat_id)
        try:
            volume = await get_volume(chat_id)
            loop_mode = await get_loop(chat_id)
            duration_str = format_duration(track.get("duration", 0))
            requested_by = track.get("requested_by", "Auto-play")

            caption = (
                f"🎵 **Now Playing**\n\n"
                f"**{track.get('title', 'Unknown')}**\n"
                f"👤 {track.get('artist', '')}\n"
                f"⏱ {duration_str}\n"
                f"🔊 Volume: {volume}%  |  🔁 Loop: {loop_mode.capitalize()}\n"
                f"📨 Requested by: {requested_by}"
            )

            # Generate thumbnail
            thumb_path = await generate_thumbnail(
                title=track.get("title", "Unknown"),
                artist=track.get("artist", ""),
                duration=duration_str,
                requested_by=requested_by,
                thumbnail_url=track.get("thumbnail"),
                output_filename=f"np_{chat_id}.png",
            )

            kb = now_playing_keyboard(chat_id, is_paused=False)
            msg = await self._bot.send_photo(
                chat_id=chat_id,
                photo=thumb_path,
                caption=caption,
                reply_markup=kb,
            )
            # Delete previous NP message
            if state.np_message_id:
                try:
                    await self._bot.delete_messages(chat_id, state.np_message_id)
                except Exception:
                    pass
            state.np_message_id = msg.id

        except Exception as e:
            log.error(f"NP card error: {e}")

    async def _send_to_chat(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id, text)
        except Exception as e:
            log.warning(f"Send message failed: {e}")


# Global singleton
music_player = MusicPlayer()
