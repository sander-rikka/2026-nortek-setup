from datetime import datetime, timedelta, timezone

from conftest import sar_event
from sig500_campaign.scheduling.optimizer import optimize_echo_phase


def test_optimizer_centers_synthetic_events():
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    events = [sar_event(str(index), start + timedelta(minutes=minute)) for index, minute in enumerate((7, 37, 67))]
    result = optimize_echo_phase(start, events, interval_seconds=1800, duration_seconds=600)
    assert result.schedule.phase_seconds == 120
    assert len(result.covered_event_ids) == 3
    assert result.minimum_edge_margin_seconds == 300


def test_official_not_sacrificed_for_prediction():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    official = sar_event("o", start + timedelta(minutes=2))
    predicted = sar_event("p", start + timedelta(minutes=20), source="predicted_from_history")
    result = optimize_echo_phase(start, [official, predicted], interval_seconds=1800, duration_seconds=600)
    assert "o" in result.covered_event_ids


def test_phase_does_not_create_virtual_pre_campaign_window():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = sar_event("early", start + timedelta(seconds=100))
    result = optimize_echo_phase(start, [event], interval_seconds=1800, duration_seconds=600)
    assert result.schedule.phase_seconds <= 100
