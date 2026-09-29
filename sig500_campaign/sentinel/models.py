from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sig500_campaign.models import ensure_utc, iso_utc


@dataclass(frozen=True)
class SarAcquisitionEvent:
    id: str
    platform: str
    sensing_start_utc: datetime
    sensing_end_utc: datetime
    representative_time_utc: datetime
    acquisition_mode: str
    orbit_direction: str | None
    relative_orbit: int | None
    source: str
    confidence: str
    source_product_names: tuple[str, ...] = ()
    pattern_id: str | None = None
    supporting_event_count: int | None = None
    recurrence_interval_seconds: float | None = None
    recurrence_mad_seconds: float | None = None
    datatake_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("sensing_start_utc", "sensing_end_utc", "representative_time_utc"):
            object.__setattr__(self, field, ensure_utc(getattr(self, field)))
        if self.sensing_end_utc < self.sensing_start_utc:
            raise ValueError("sensing end precedes sensing start")
        if self.acquisition_mode not in {"IW", "EW"}:
            raise ValueError("only IW and EW SAR acquisitions are supported")
        if self.source not in {"historical_actual", "official_plan", "predicted_from_history"}:
            raise ValueError("invalid SAR event source")

    @classmethod
    def from_interval(cls, *, sensing_start_utc: datetime, sensing_end_utc: datetime, **kwargs):
        representative = sensing_start_utc + (sensing_end_utc - sensing_start_utc) / 2
        return cls(
            sensing_start_utc=sensing_start_utc,
            sensing_end_utc=sensing_end_utc,
            representative_time_utc=representative,
            **kwargs,
        )

    def as_dict(self) -> dict:
        result = asdict(self)
        for key in ("sensing_start_utc", "sensing_end_utc", "representative_time_utc"):
            result[key] = iso_utc(result[key])
        result["source_product_names"] = list(self.source_product_names)
        return result
