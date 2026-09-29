from __future__ import annotations

from .models import CurrentSchedule, EchoSchedule, generate_windows


def resolve_current_schedule(
    echo: EchoSchedule,
    interval_seconds: int | None,
    duration_seconds: int | None,
    *,
    enabled: bool = True,
) -> CurrentSchedule:
    inherited = interval_seconds is None and duration_seconds is None
    interval = echo.interval_seconds if interval_seconds is None else interval_seconds
    duration = echo.duration_seconds if duration_seconds is None else duration_seconds
    phase = echo.phase_seconds if inherited else 0
    return CurrentSchedule(interval, duration, phase, enabled, inherited)


__all__ = ["CurrentSchedule", "generate_windows", "resolve_current_schedule"]
