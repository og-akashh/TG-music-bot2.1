"""
settings.py — Central configuration loader.
All values are pulled from environment variables with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── Telegram credentials ──────────────────────────────────────────────
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    SESSION_STRING: str = os.getenv("SESSION_STRING", "")  # Pyrogram user session

    # ── Database ──────────────────────────────────────────────────────────
    DB_URI: str = os.getenv("DB_URI", "mongodb://localhost:27017")
    DB_NAME: str = os.getenv("DB_NAME", "musicbot")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Spotify API ───────────────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    # ── Lyrics API ────────────────────────────────────────────────────────
    GENIUS_API_TOKEN: str = os.getenv("GENIUS_API_TOKEN", "")

    # ── Bot behaviour ─────────────────────────────────────────────────────
    BOT_NAME: str = os.getenv("BOT_NAME", "MusicBot")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    LOG_CHANNEL: int = int(os.getenv("LOG_CHANNEL", "0"))

    # Cache directory for downloaded audio
    CACHE_DIR: str = os.getenv("CACHE_DIR", "./cache")
    MAX_CACHE_SIZE_MB: int = int(os.getenv("MAX_CACHE_SIZE_MB", "2048"))

    # Audio quality (bestaudio / 128k / 320k)
    AUDIO_QUALITY: str = os.getenv("AUDIO_QUALITY", "bestaudio")

    # Queue / playback limits
    MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "100"))
    MAX_PLAYLIST_SIZE: int = int(os.getenv("MAX_PLAYLIST_SIZE", "50"))
    STREAM_TIMEOUT: int = int(os.getenv("STREAM_TIMEOUT", "300"))   # seconds

    # Auto-play related songs when queue ends
    AUTO_PLAY: bool = os.getenv("AUTO_PLAY", "true").lower() == "true"

    # Default language
    DEFAULT_LANG: str = os.getenv("DEFAULT_LANG", "en")

    # Dashboard
    DASHBOARD_ENABLED: bool = os.getenv("DASHBOARD_ENABLED", "false").lower() == "true"
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8080"))
    DASHBOARD_SECRET: str = os.getenv("DASHBOARD_SECRET", "change_me_in_production")

    # ffmpeg path (override if not in PATH)
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")

    @classmethod
    def validate(cls) -> None:
        """Raise immediately on missing critical values."""
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.SESSION_STRING:
            missing.append("SESSION_STRING")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example → .env and fill in the values."
            )
        os.makedirs(cls.CACHE_DIR, exist_ok=True)


config = Settings()
