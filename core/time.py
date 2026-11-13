"""Time and duration parsing utilities."""

from __future__ import annotations

import re
from datetime import timedelta

TIME_REGEX = re.compile(
    r"^"
    r"((?P<weeks>\d+?)\s*(?:weeks?|w))?"
    r"((?P<days>\d+?)\s*(?:days?|d))?"
    r"((?P<hours>\d+?)\s*(?:hours?|hrs?|h))?"
    r"((?P<minutes>\d+?)\s*(?:minutes?|mins?|m))?"
    r"((?P<seconds>\d+?)\s*(?:seconds?|secs?|s))?"
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
