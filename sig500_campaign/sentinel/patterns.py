from __future__ import annotations

import hashlib
import statistics
from dataclasses import asdict, dataclass

from .models import SarAcquisitionEvent


@dataclass(frozen=True)
class RepeatPattern:
    pattern_id: str
    platform: str
    relative_orbit: int | None
    orbit_direction: str | None
    acquisition_mode: str
    status: str
    event_count: int
    interval_count: int
    median_recurrence_seconds: float | None
    mad_seconds: float | None
    min_interval_seconds: float | None
    max_interval_seconds: float | None
    last_event: SarAcquisitionEvent

    def as_dict(self) -> dict:
        result = asdict(self)
        result["last_event"] = self.last_event.as_dict()
        return result


def analyze_repeat_patterns(
    events: list[SarAcquisitionEvent], *, min_events: int = 3, max_mad_minutes: float = 30
) -> list[RepeatPattern]:
    groups: dict[tuple, list[SarAcquisitionEvent]] = {}
    for event in events:
        key = (event.platform, event.relative_orbit, event.orbit_direction, event.acquisition_mode)
        groups.setdefault(key, []).append(event)
    patterns = []
    for key, group in groups.items():
        group.sort(key=lambda item: item.representative_time_utc)
        intervals = [
            (right.representative_time_utc - left.representative_time_utc).total_seconds()
            for left, right in zip(group, group[1:])
        ]
        median = statistics.median(intervals) if intervals else None
        mad = statistics.median(abs(value - median) for value in intervals) if intervals else None
        if len(group) < min_events:
            status = "insufficient_data"
        elif mad is not None and mad <= max_mad_minutes * 60:
            status = "clear"
        else:
            status = "uncertain"
        identifier = hashlib.sha1("|".join(map(str, key)).encode()).hexdigest()[:10]
        patterns.append(
            RepeatPattern(
                f"pattern-{identifier}",
                key[0], key[1], key[2], key[3], status,
                len(group), len(intervals), median, mad,
                min(intervals) if intervals else None,
                max(intervals) if intervals else None,
                group[-1],
            )
        )
    return sorted(patterns, key=lambda item: item.pattern_id)
