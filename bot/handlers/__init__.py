"""
handlers/__init__.py

Importing this package causes every handler module to be executed,
which registers all @Client.on_message and @Client.on_callback_query
decorators with Pyrogram.  Import order matters only where two handlers
share the same filter; generally keep alphabetical order.
"""

from . import (
    admin,
    callbacks,
    controls,
    lyrics_handler,
    play,
    playlist_handler,
    queue_handler,
    settings_handler,
    start,
)

__all__ = [
    "admin",
    "callbacks",
    "controls",
    "lyrics_handler",
    "play",
    "playlist_handler",
    "queue_handler",
    "settings_handler",
    "start",
]
