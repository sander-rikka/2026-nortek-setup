from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sig500_campaign.models import ensure_utc, iso_utc


@dataclass(frozen=True)
class EchoSchedule:
    interval_seconds: int
    duration_seconds: int
    phase_seconds: int = 0
    sample_rate_hz: float = 4.0

    def __post_init__(self) -> None:
        if self.sample_rate_hz != 4.0:
            raise ValueError("Signature500 echosounder sample rate must be exactly 4 Hz")
        _validate_timing(self.interval_seconds, self.duration_seconds, self.phase_seconds)
        if self.duration_seconds * self.sample_rate_hz != int(self.duration_seconds * self.sample_rate_hz):
            raise ValueError("echo window must contain an integer number of samples")

    @property
    def samples_per_window(self) -> int:
        return int(self.duration_seconds * self.sample_rate_hz)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CurrentSchedule:
    interval_seconds: int
    duration_seconds: int
    phase_seconds: int = 0
    enabled: bool = True
    inherited_from_echo: bool = False

    def __post_init__(self) -> None:
        _validate_timing(self.interval_seconds, self.duration_seconds, self.phase_seconds)

    def as_dict(self) -> dict:
        return asdict(self)


def _validate_timing(interval_seconds: int, duration_seconds: int, phase_seconds: int) -> None:
    if interval_seconds <= 0 or duration_seconds <= 0:
        raise ValueError("interval and duration must be positive")
    if duration_seconds > interval_seconds:
        raise ValueError("duration must not exceed interval")
    if not 0 <= phase_seconds < interval_seconds:
        raise ValueError("phase must satisfy 0 <= phase < interval")


@dataclass(frozen=True)
class MeasurementWindow:
    schedule_type: str
    window_number: int
    window_type: str
    start: datetime
    end: datetime
    duration_seconds: float
    interval_seconds: int | None
    sample_rate_hz: float | None
    samples: int | None
    sar_event_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        result = asdict(self)
        result["start_utc"] = iso_utc(self.start)
        result["end_utc"] = iso_utc(self.end)
        result.pop("start")
        result.pop("end")
        result["sar_overlap"] = bool(self.sar_event_ids)
        result["sar_event_ids"] = ";".join(self.sar_event_ids)
        return result


def generate_windows(
    campaign_start: datetime,
    campaign_end: datetime,
    schedule: EchoSchedule | CurrentSchedule,
    *,
    schedule_type: str,
) -> list[MeasurementWindow]:
    campaign_start = ensure_utc(campaign_start)
    campaign_end = ensure_utc(campaign_end)
    if campaign_end <= campaign_start:
        raise ValueError("campaign end must be after start")
    if isinstance(schedule, CurrentSchedule) and not schedule.enabled:
        return []
    windows: list[MeasurementWindow] = []
    nominal_start = campaign_start.timestamp() + schedule.phase_seconds
    index = 0
    while nominal_start < campaign_end.timestamp():
        nominal_end = nominal_start + schedule.duration_seconds
        clipped_start = max(nominal_start, campaign_start.timestamp())
        clipped_end = min(nominal_end, campaign_end.timestamp())
        if clipped_end > clipped_start:
            sample_rate = schedule.sample_rate_hz if isinstance(schedule, EchoSchedule) else None
            samples = (
                int((clipped_end - clipped_start) * schedule.sample_rate_hz)
                if isinstance(schedule, EchoSchedule)
                else None
            )
            windows.append(
                MeasurementWindow(
                    schedule_type,
                    index + 1,
                    "periodic",
                    datetime.fromtimestamp(clipped_start, tz=campaign_start.tzinfo),
                    datetime.fromtimestamp(clipped_end, tz=campaign_start.tzinfo),
                    clipped_end - clipped_start,
                    schedule.interval_seconds,
                    sample_rate,
                    samples,
                )
            )
        nominal_start += schedule.interval_seconds
        index += 1
    return windows
