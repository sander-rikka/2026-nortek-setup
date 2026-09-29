from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit timezone")
    return value.astimezone(timezone.utc)


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 datetime: {value}") from exc
    return ensure_utc(parsed)


def iso_utc(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Campaign:
    start: datetime
    end: datetime
    water_depth_m: float
    head_height_above_bottom_m: float
    latitude: float
    longitude: float
    surface_margin_m: float = 2.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", ensure_utc(self.start))
        object.__setattr__(self, "end", ensure_utc(self.end))
        if self.end <= self.start:
            raise ValueError("campaign end must be after start")
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")

    def as_dict(self) -> dict:
        result = asdict(self)
        result["start"] = iso_utc(self.start)
        result["end"] = iso_utc(self.end)
        return result
