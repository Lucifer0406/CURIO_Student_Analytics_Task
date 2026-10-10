"""Turn numbers into display strings. Calculations never format; the UI never calculates."""
import math


def format_duration(seconds) -> str:
    """5430 -> '1h 31m', 2700 -> '45m', 0 -> '0m'. Rounds half-minutes up.

    Not round(): Python rounds .5 to the nearest EVEN number, so 30 s would show '0m'.
    """
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "—"
    minutes = math.floor(seconds / 60 + 0.5)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def format_pct(value, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:.{decimals}f}%"
