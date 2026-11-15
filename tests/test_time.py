"""Unit tests for time and duration parsing utilities."""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.time import format_duration, parse_duration


@pytest.mark.parametrize(
    ("input_str", "expected_seconds"),
    [
        ("30s", 30),
        ("45sec", 45),
        ("15seconds", 15),
        ("10m", 600),
        ("5mins", 300),
        ("1h", 3600),
        ("12hrs", 43200),
        ("1d", 86400),
        ("3days", 259200),
        ("1w", 604800),
        ("2weeks", 1209600),
        ("1d12h", 86400 + 43200),
        ("1d 12h", 86400 + 43200),
        ("2h30m10s", 7200 + 1800 + 10),
        ("2h 30m 10s", 7200 + 1800 + 10),
    ],
)
def test_parse_duration_valid(input_str: str, expected_seconds: int) -> None:
    """Verify that human duration strings parse to exact timedelta values."""
    result = parse_duration(input_str)
    assert result is not None
    assert result == timedelta(seconds=expected_seconds)


@pytest.mark.parametrize(
    "invalid_input",
    [
        "",
        "   ",
        "invalid",
        "-10m",
        "0s",
        "hello",
        "10years",
    ],
)
def test_parse_duration_invalid(invalid_input: str) -> None:
    """Verify that malformed or zero duration strings return None."""
    assert parse_duration(invalid_input) is None


@pytest.mark.parametrize(
    ("seconds", "expected_str"),
    [
        (0, "0 seconds"),
        (-5, "0 seconds"),
        (10, "10 seconds"),
        (1, "1 second"),
        (60, "1 minute"),
        (120, "2 minutes"),
        (65, "1 minute 5 seconds"),
        (3600, "1 hour"),
        (7200, "2 hours"),
        (3665, "1 hour 1 minute 5 seconds"),
        (21600, "6 hours"),
    ],
)
def test_format_duration(seconds: int, expected_str: str) -> None:
    """Verify seconds format into human-readable duration strings."""
    assert format_duration(seconds) == expected_str
