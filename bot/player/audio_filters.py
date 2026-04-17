"""
audio_filters.py — ffmpeg audio filter presets.

Each filter returns an ffmpeg filter-graph string suitable for
use in pytgcalls / ffmpeg subprocess.
"""

from typing import Optional

FILTERS: dict = {
    "none": None,
    "bassboost": "equalizer=f=40:width_type=o:width=2:g=15,equalizer=f=80:width_type=o:width=2:g=8",
    "nightcore": "aresample=48000,asetrate=48000*1.25,atempo=1.0",
    "echo": "aecho=0.8:0.9:100:0.3",
    "8d": "apulsator=hz=0.125",
    "earrape": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1",
    "vaporwave": "aresample=48000,asetrate=48000*0.8,atempo=1.0",
    "karaoke": "pan=stereo|c0=c0-c1|c1=c1-c0",
    "loud": "loudnorm=I=-5:TP=-2:LRA=7",
}

FILTER_NAMES = {
    "none": "No Filter",
    "bassboost": "Bass Boost",
    "nightcore": "Nightcore",
    "echo": "Echo",
    "8d": "8D Audio",
    "earrape": "Earrape",
    "vaporwave": "Vaporwave",
    "karaoke": "Karaoke",
    "loud": "Loud Normalise",
}


def get_filter(name: str) -> Optional[str]:
    """Return the ffmpeg filter string for a named preset (None = passthrough)."""
    return FILTERS.get(name.lower())


def build_ffmpeg_options(
    seek: int = 0,
    filter_name: str = "none",
    volume: int = 100,
) -> dict:
    """
    Build pytgcalls-compatible ffmpeg_parameters dict.

    Args:
        seek        : start offset in seconds
        filter_name : one of FILTERS keys
        volume      : percentage 1-200

    Returns dict passed to pytgcalls as ffmpeg_parameters.
    """
    filters = []

    # Volume via ffmpeg (avoids re-encoding quality loss)
    if volume != 100:
        vol_ratio = round(volume / 100, 2)
        filters.append(f"volume={vol_ratio}")

    af_str = get_filter(filter_name)
    if af_str:
        filters.append(af_str)

    options = {
        "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -b:a 128k",
    }

    if seek > 0:
        options["before_options"] += f" -ss {seek}"

    if filters:
        options["options"] += f" -af \"{','.join(filters)}\""

    return options
