from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sig500_campaign.models import iso_utc
from sig500_campaign.sentinel.models import SarAcquisitionEvent

from .models import MeasurementWindow


@dataclass(frozen=True)
class Collocation:
    sar_event_id: str
    acquisition_time_utc: datetime
    platform: str
    acquisition_mode: str
    relative_orbit: int | None
    orbit_direction: str | None
    sar_source: str
    sar_confidence: str
    pattern_id: str | None
    echo_active: bool
    echo_window_number: int | None
    echo_window_start_utc: datetime | None
    echo_window_end_utc: datetime | None
    echo_offset_from_center_seconds: float | None
    echo_edge_margin_seconds: float | None
    current_active: bool
    current_window_number: int | None
    current_window_start_utc: datetime | None
    current_window_end_utc: datetime | None
    joint_collocation: bool
    padding_any_overlap: bool
    padding_full_coverage: bool
    padding_fraction_covered: float

    def as_dict(self) -> dict:
        result = asdict(self)
        for key, value in list(result.items()):
            if isinstance(value, datetime):
                result[key] = iso_utc(value)
        return result


def _containing(windows: list[MeasurementWindow], time: datetime) -> MeasurementWindow | None:
    return next((window for window in windows if window.start <= time < window.end), None)


def collocate_events(
    events: list[SarAcquisitionEvent],
    echo_windows: list[MeasurementWindow],
    current_windows: list[MeasurementWindow],
    *,
    padding_seconds: float = 0,
) -> list[Collocation]:
    collocations: list[Collocation] = []
    for event in sorted(events, key=lambda item: item.representative_time_utc):
        time = event.representative_time_utc
        echo = _containing(echo_windows, time)
        current = _containing(current_windows, time)
        desired_start = time - timedelta(seconds=padding_seconds)
        desired_end = time + timedelta(seconds=padding_seconds)
        overlaps = []
        for window in echo_windows:
            seconds = max(0.0, (min(window.end, desired_end) - max(window.start, desired_start)).total_seconds())
            if seconds:
                overlaps.append(seconds)
        desired_seconds = padding_seconds * 2
        overlap_seconds = min(desired_seconds, sum(overlaps)) if desired_seconds else float(bool(echo))
        fraction = overlap_seconds / desired_seconds if desired_seconds else float(bool(echo))
        full = bool(echo) if not padding_seconds else fraction >= 1.0
        if echo:
            center = echo.start + (echo.end - echo.start) / 2
            offset = (time - center).total_seconds()
            margin = min((time - echo.start).total_seconds(), (echo.end - time).total_seconds())
        else:
            offset = margin = None
        collocations.append(
            Collocation(
                event.id,
                time,
                event.platform,
                event.acquisition_mode,
                event.relative_orbit,
                event.orbit_direction,
                event.source,
                event.confidence,
                event.pattern_id,
                echo is not None,
                echo.window_number if echo else None,
                echo.start if echo else None,
                echo.end if echo else None,
                offset,
                margin,
                current is not None,
                current.window_number if current else None,
                current.start if current else None,
                current.end if current else None,
                echo is not None and current is not None,
                overlap_seconds > 0,
                full,
                fraction,
            )
        )
    return collocations


def summarize_collocations(items: list[Collocation]) -> dict[str, int | float]:
    total = len(items)
    echo = sum(item.echo_active for item in items)
    current = sum(item.current_active for item in items)
    joint = sum(item.joint_collocation for item in items)
    official = [item for item in items if item.sar_source == "official_plan"]
    predicted = [item for item in items if item.sar_source == "predicted_from_history"]
    return {
        "total_sar_acquisitions_during_deployment": total,
        "total_echo_collocations": echo,
        "total_current_collocations": current,
        "total_joint_collocations": joint,
        "uncovered_by_echo": total - echo,
        "uncovered_by_current": total - current,
        "official_planned_acquisitions": len(official),
        "official_echo_collocations": sum(item.echo_active for item in official),
        "predicted_acquisitions": len(predicted),
        "predicted_echo_collocations": sum(item.echo_active for item in predicted),
        "echo_collocation_fraction": echo / total if total else 0.0,
        "joint_collocation_fraction": joint / total if total else 0.0,
    }
