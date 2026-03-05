"""Time formatting utilities for displaying durations throughout the app.

Converts seconds/minutes to human-readable formats like "1h 30m", "5 min", or "05:30".
Use TimeFormatter.seconds_to_display() for stats, seconds_to_hms() for timers.
"""


class TimeFormatter:
    """Unified time formatting utilities for the application."""

    @staticmethod
    def seconds_to_short(seconds: int) -> str:
        """Convert seconds to short format like '5s', '5m', or '1h 30m'."""
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
        return f"{mins}m"

    @staticmethod
    def seconds_to_display(seconds: int) -> str:
        """Convert seconds to display format like '5 min' or '1h 30m'."""
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min"
        h, m = divmod(minutes, 60)
        return f"{h}h" if m == 0 else f"{h}h {m}m"

    @staticmethod
    def minutes_to_display(minutes: int) -> str:
        """Convert minutes to verbose format like '5 min' or '1 hr 30 min'."""
        if minutes < 60:
            return f"{minutes} min"
        h, m = divmod(minutes, 60)
        if m == 0:
            return f"{h} hr" if h == 1 else f"{h} hrs"
        return f"{h} hr {m} min" if h == 1 else f"{h} hrs {m} min"

    @staticmethod
    def seconds_to_timer(seconds: int) -> str:
        """Convert seconds to timer display format like '05:30'."""
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def seconds_to_hms(seconds: int) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
