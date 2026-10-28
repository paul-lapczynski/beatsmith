"""Validate explicit tempo overrides before creating chart files."""
import math


def validate_bpm(value: float | None) -> float | None:
    if value is None or value == 0:
        return None
    if not math.isfinite(value) or value < 20:
        raise ValueError("BPM must be at least 20. Choose detect/auto to find the song's tempo.")
    return value
