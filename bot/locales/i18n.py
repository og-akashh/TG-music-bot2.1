"""
i18n.py — Simple file-based internationalisation system.

Usage:
    from bot.locales.i18n import get_text
    text = get_text("now_playing", lang="en", title="Song", duration="3:45", ...)
"""

import json
import os
from functools import lru_cache
from typing import Dict

_LOCALE_DIR = os.path.dirname(__file__)


@lru_cache(maxsize=16)
def _load_locale(lang: str) -> Dict[str, str]:
    path = os.path.join(_LOCALE_DIR, f"{lang}.json")
    fallback = os.path.join(_LOCALE_DIR, "en.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        with open(fallback, "r", encoding="utf-8") as f:
            return json.load(f)


def get_text(key: str, lang: str = "en", **kwargs) -> str:
    """
    Fetch a localised string and format it with **kwargs.

    Falls back to English if the key is missing in the requested locale.
    Falls back to the raw key if not found in English either.
    """
    locale = _load_locale(lang)
    en_locale = _load_locale("en")
    template = locale.get(key) or en_locale.get(key) or key
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def available_languages() -> list:
    return [
        f.replace(".json", "")
        for f in os.listdir(_LOCALE_DIR)
        if f.endswith(".json")
    ]
