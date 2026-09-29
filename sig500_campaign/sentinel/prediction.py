from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta

from .models import SarAcquisitionEvent
from .patterns import RepeatPattern


class HistoricalRepeatPredictionProvider:
    def predict(
        self,
        patterns: list[RepeatPattern],
        start: datetime,
        end: datetime,
        *,
        official_coverage_end: datetime | None = None,
    ) -> list[SarAcquisitionEvent]:
        predictions = []
        floor = max(start, official_coverage_end) if official_coverage_end else start
        for pattern in patterns:
            if pattern.status != "clear" or not pattern.median_recurrence_seconds:
                continue
            recurrence = pattern.median_recurrence_seconds
            time = pattern.last_event.representative_time_utc
            while time < floor:
                time += timedelta(seconds=recurrence)
            duration = pattern.last_event.sensing_end_utc - pattern.last_event.sensing_start_utc
            while time < end:
                confidence = "medium" if (pattern.mad_seconds or 0) <= 300 and pattern.event_count >= 5 else "low"
                identity = f"{pattern.pattern_id}|{time.isoformat()}"
                predictions.append(
                    SarAcquisitionEvent.from_interval(
                        id="predicted-" + hashlib.sha1(identity.encode()).hexdigest()[:12],
                        platform=pattern.platform,
                        sensing_start_utc=time - duration / 2,
                        sensing_end_utc=time + duration / 2,
                        acquisition_mode=pattern.acquisition_mode,
                        orbit_direction=pattern.orbit_direction,
                        relative_orbit=pattern.relative_orbit,
                        source="predicted_from_history",
                        confidence=confidence,
                        pattern_id=pattern.pattern_id,
                        supporting_event_count=pattern.event_count,
                        recurrence_interval_seconds=recurrence,
                        recurrence_mad_seconds=pattern.mad_seconds,
                    )
                )
                time += timedelta(seconds=recurrence)
        return sorted(predictions, key=lambda item: item.representative_time_utc)


def merge_future_events(
    official: list[SarAcquisitionEvent], predicted: list[SarAcquisitionEvent], *, tolerance_seconds: float = 300
) -> list[SarAcquisitionEvent]:
    result = list(official)
    for prediction in predicted:
        duplicate = any(
            abs((item.representative_time_utc - prediction.representative_time_utc).total_seconds()) <= tolerance_seconds
            and (item.platform == prediction.platform)
            and (item.relative_orbit is None or prediction.relative_orbit is None or item.relative_orbit == prediction.relative_orbit)
            and item.acquisition_mode == prediction.acquisition_mode
            for item in official
        )
        if not duplicate:
            result.append(prediction)
    return sorted(result, key=lambda item: item.representative_time_utc)
