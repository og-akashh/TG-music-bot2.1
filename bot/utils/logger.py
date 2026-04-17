"""
logger.py — Structured async-safe logging.

• Console  : coloured output via rich
• File     : rotating log file (logs/bot.log)
• Telegram : critical errors forwarded to LOG_CHANNEL
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler

_console = Console()

os.makedirs("logs", exist_ok=True)

_file_handler = RotatingFileHandler(
    "logs/bot.log",
    maxBytes=5 * 1024 * 1024,   # 5 MB
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
)

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        RichHandler(console=_console, rich_tracebacks=True, show_path=False),
        _file_handler,
    ],
)

# Silence noisy third-party loggers
for _noisy in ("pyrogram", "pytgcalls", "asyncio", "httpx", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger inheriting root configuration."""
    return logging.getLogger(name)


LOGGER = get_logger("MusicBot")
