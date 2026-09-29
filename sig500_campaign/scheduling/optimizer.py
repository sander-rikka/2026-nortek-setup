from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sig500_campaign.sentinel.models import SarAcquisitionEvent

from .models import EchoSchedule


@dataclass(frozen=True)
class OptimizationResult:
    schedule: EchoSchedule
    covered_event_ids: tuple[str, ...]
    official_covered: int
    minimum_edge_margin_seconds: float
    total_absolute_center_offset_seconds: float


def _window_for_time(start: datetime, schedule: EchoSchedule, event_time: datetime) -> tuple[datetime, datetime]:
    elapsed = (event_time - start).total_seconds() - schedule.phase_seconds
    index = max(0, int(elapsed // schedule.interval_seconds))
    window_start = start + timedelta(seconds=schedule.phase_seconds + index * schedule.interval_seconds)
    return window_start, window_start + timedelta(seconds=schedule.duration_seconds)


def _coverage(
    event: SarAcquisitionEvent,
    start: datetime,
    schedule: EchoSchedule,
    padding_seconds: float,
    mode: str,
) -> tuple[bool, float, float]:
    time = event.representative_time_utc
    window_start, window_end = _window_for_time(start, schedule, time)
    desired_start = time - timedelta(seconds=padding_seconds)
    desired_end = time + timedelta(seconds=padding_seconds)
    point = window_start <= time < window_end
    overlap = max(0.0, (min(window_end, desired_end) - max(window_start, desired_start)).total_seconds())
    if mode == "point":
        covered = point
    elif mode == "any":
        covered = overlap > 0 if padding_seconds else point
    elif mode == "full":
        covered = window_start <= desired_start and desired_end <= window_end
    else:
        raise ValueError("coverage mode must be point, any, or full")
    margin = min((time - window_start).total_seconds(), (window_end - time).total_seconds()) if point else -1.0
    center_offset = abs((time - (window_start + (window_end - window_start) / 2)).total_seconds()) if point else 0.0
    return covered, margin, center_offset


def optimize_echo_phase(
    campaign_start: datetime,
    events: list[SarAcquisitionEvent],
    *,
    interval_seconds: int,
    duration_seconds: int,
    resolution_seconds: int = 1,
    padding_seconds: float = 0,
    coverage_mode: str = "point",
) -> OptimizationResult:
    if resolution_seconds <= 0:
        raise ValueError("phase resolution must be positive")
    relevant = [event for event in events if event.representative_time_utc >= campaign_start]
    best: tuple | None = None
    best_result: OptimizationResult | None = None
    for phase in range(0, interval_seconds, resolution_seconds):
        schedule = EchoSchedule(interval_seconds, duration_seconds, phase)
        covered: list[str] = []
        margins: list[float] = []
        offsets: list[float] = []
        official = 0
        for event in relevant:
            is_covered, margin, offset = _coverage(
                event, campaign_start, schedule, padding_seconds, coverage_mode
            )
            if is_covered:
                covered.append(event.id)
                if event.source == "official_plan":
                    official += 1
                if margin >= 0:
                    margins.append(margin)
                    offsets.append(offset)
        minimum_margin = min(margins) if margins else -1.0
        offset_sum = sum(offsets)
        score = (official, len(covered), minimum_margin, -offset_sum, -phase)
        if best is None or score > best:
            best = score
            best_result = OptimizationResult(schedule, tuple(covered), official, minimum_margin, offset_sum)
    assert best_result is not None
    return best_result
