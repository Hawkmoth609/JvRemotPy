"""Helper utilities for JvRemotPy."""

import datetime


def get_timestamp():
    """Returns current timestamp as ISO string."""
    return datetime.datetime.now().isoformat()


def format_result(data):
    """Formats a dict or value for display."""
    if not isinstance(data, dict):
        return str(data)

    lines = []
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def safe_int(value, default=0):
    """Safely converts value to int, returns default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
