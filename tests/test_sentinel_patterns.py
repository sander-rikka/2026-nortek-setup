from datetime import datetime, timedelta, timezone

from conftest import sar_event
from sig500_campaign.sentinel.patterns import analyze_repeat_patterns
from sig500_campaign.sentinel.prediction import HistoricalRepeatPredictionProvider, merge_future_events


def test_regular_irregular_and_too_few_patterns():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    regular = [sar_event(f"r{i}", start + timedelta(days=12 * i), source="historical_actual") for i in range(4)]
    irregular = [sar_event(f"i{i}", start + timedelta(days=value), source="historical_actual", orbit=88) for i, value in enumerate((0, 12, 27, 40))]
    few = [sar_event(f"f{i}", start + timedelta(days=12 * i), source="historical_actual", orbit=89) for i in range(2)]
    patterns = analyze_repeat_patterns(regular + irregular + few, max_mad_minutes=30)
    by_orbit = {pattern.relative_orbit: pattern for pattern in patterns}
    assert by_orbit[87].status == "clear"
    assert by_orbit[88].status == "uncertain"
    assert by_orbit[89].status == "insufficient_data"


def test_orbit_direction_and_mode_are_separate():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = [
        sar_event("a", start, source="historical_actual"),
        sar_event("d", start, source="historical_actual", direction="DESCENDING"),
        sar_event("e", start, source="historical_actual", mode="EW"),
    ]
    assert len(analyze_repeat_patterns(events)) == 3


def test_prediction_provenance_and_official_precedence():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    history = [sar_event(str(i), start + timedelta(days=12 * i), source="historical_actual") for i in range(5)]
    pattern = analyze_repeat_patterns(history)[0]
    future_start = start + timedelta(days=60)
    predicted = HistoricalRepeatPredictionProvider().predict([pattern], future_start, future_start + timedelta(days=1))
    assert predicted[0].source == "predicted_from_history"
    assert predicted[0].pattern_id == pattern.pattern_id
    official = sar_event("official", predicted[0].representative_time_utc)
    merged = merge_future_events([official], predicted)
    assert [event.id for event in merged] == ["official"]
