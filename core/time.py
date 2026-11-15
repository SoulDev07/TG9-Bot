"""Time and duration parsing utilities."""

from __future__ import annotations

import re
from datetime import timedelta

TIME_REGEX = re.compile(
    r"^\s*"
    r"((?P<weeks>\d+)\s*(?:weeks?|w)[\s,]*)?"
    r"((?P<days>\d+)\s*(?:days?|d)[\s,]*)?"
    r"((?P<hours>\d+)\s*(?:hours?|hrs?|h)[\s,]*)?"
    r"((?P<minutes>\d+)\s*(?:minutes?|mins?|m)[\s,]*)?"
    r"((?P<seconds>\d+)\s*(?:seconds?|secs?|s)[\s,]*)?"
    r"$",
    re.IGNORECASE,
)


def parse_duration(duration_str: str) -> timedelta | None:
    """Parse a human-friendly duration string (e.g., '1d', '12h', '30m', '2w') into a timedelta.

    Returns None if the format is invalid or represents zero duration.
    """
    clean_str = duration_str.strip().lower()
    if not clean_str:
        return None

    match = TIME_REGEX.match(clean_str)
    if not match:
        return None

    time_dict = {unit: int(value) for unit, value in match.groupdict().items() if value}
    if not time_dict:
        return None

    delta = timedelta(**time_dict)
    return delta if delta.total_seconds() > 0 else None


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds <= 0:
        return "0 seconds"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    return " ".join(parts)
