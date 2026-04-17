"""
formatters.py — Utility formatting functions.
"""

import re
from datetime import timedelta
from typing import List

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def format_duration(seconds: int) -> str:
    """Convert seconds → HH:MM:SS or MM:SS string."""
    if seconds <= 0:
        return "0:00"
    td = timedelta(seconds=seconds)
    total = int(td.total_seconds())
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_time_to_seconds(time_str: str) -> int:
    """
    Parse time strings like '1:30', '90', '1:30:00' → seconds.
    Returns -1 on failure.
    """
    time_str = time_str.strip()
    try:
        # Plain number
        return int(time_str)
    except ValueError:
        pass
    # MM:SS or HH:MM:SS
    parts = time_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return -1


def truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    return text[:max_len - 3] + "..." if len(text) > max_len else text


def build_progress_bar(current: int, total: int, width: int = 12) -> str:
    """Build a Unicode progress bar: ▓▓▓▓░░░░░░░░ 1:23 / 3:45"""
    if total <= 0:
        return "░" * width
    filled = int(width * current / total)
    bar = "▓" * filled + "░" * (width - filled)
    return f"{bar} {format_duration(current)} / {format_duration(total)}"


def build_queue_text(tracks: List[dict], offset: int = 0) -> str:
    """Format a list of track dicts into a readable queue string."""
    lines = []
    for i, track in enumerate(tracks, start=offset + 1):
        title = truncate(track.get("title", "Unknown"), 45)
        duration = format_duration(track.get("duration", 0))
        lines.append(f"`{i}.` **{title}** — {duration}")
    return "\n".join(lines) if lines else "_Queue is empty_"


def is_url(text: str) -> bool:
    pattern = re.compile(
        r"(https?://)?(www\.)?"
        r"(youtube\.com|youtu\.be|spotify\.com|soundcloud\.com|"
        r"open\.spotify\.com|music\.youtube\.com)"
        r"[\w\-._~:/?#\[\]@!$&'()*+,;=%]+"
    )
    return bool(pattern.match(text.strip()))


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url


def is_spotify_url(url: str) -> bool:
    return "spotify.com" in url or "open.spotify.com" in url


def is_soundcloud_url(url: str) -> bool:
    return "soundcloud.com" in url


# ── Inline keyboard builders ──────────────────────────────────────────────────

def now_playing_keyboard(chat_id: int, is_paused: bool = False) -> InlineKeyboardMarkup:
    play_pause = "▶️ Resume" if is_paused else "⏸ Pause"
    play_pause_cb = f"resume_{chat_id}" if is_paused else f"pause_{chat_id}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏮ Prev", callback_data=f"prev_{chat_id}"),
            InlineKeyboardButton(play_pause, callback_data=play_pause_cb),
            InlineKeyboardButton("⏭ Skip", callback_data=f"skip_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔉 Vol-", callback_data=f"vol_down_{chat_id}"),
            InlineKeyboardButton("⏹ Stop", callback_data=f"stop_{chat_id}"),
            InlineKeyboardButton("🔊 Vol+", callback_data=f"vol_up_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔁 Loop", callback_data=f"loop_{chat_id}"),
            InlineKeyboardButton("📋 Queue", callback_data=f"queue_{chat_id}"),
            InlineKeyboardButton("🔀 Shuffle", callback_data=f"shuffle_{chat_id}"),
        ],
    ])


def settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AutoPlay", callback_data=f"settings_autoplay_{chat_id}"),
            InlineKeyboardButton("🔐 Admin Mode", callback_data=f"settings_adminmode_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🌐 Language", callback_data=f"settings_lang_{chat_id}"),
            InlineKeyboardButton("🎚 Default Filter", callback_data=f"settings_filter_{chat_id}"),
        ],
        [InlineKeyboardButton("❌ Close", callback_data=f"settings_close_{chat_id}")],
    ])


def filter_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    filters = [
        ("🎸 Bass Boost", "bassboost"),
        ("🌙 Nightcore", "nightcore"),
        ("🌊 Echo", "echo"),
        ("📻 8D Audio", "8d"),
        ("⬆️ Earrape", "earrape"),
        ("❌ Remove Filter", "none"),
    ]
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"filter_{name}_{chat_id}")]
        for label, name in filters
    ]
    buttons.append([InlineKeyboardButton("« Back", callback_data=f"np_{chat_id}")])
    return InlineKeyboardMarkup(buttons)
