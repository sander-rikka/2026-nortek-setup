from datetime import datetime, timedelta, timezone

from conftest import sar_event
from sig500_campaign.scheduling.collocations import collocate_events, summarize_collocations
from sig500_campaign.scheduling.models import CurrentSchedule, EchoSchedule, generate_windows


def test_boundaries_and_three_collocation_types():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    echo = generate_windows(start, end, EchoSchedule(1800, 600), schedule_type="echo")
    current = generate_windows(start, end, CurrentSchedule(1800, 600, 600), schedule_type="current")
    events = [
        sar_event("echo", start),
        sar_event("current", start + timedelta(minutes=10)),
        sar_event("none", start + timedelta(minutes=20)),
        sar_event("joint", start + timedelta(minutes=30)),
    ]
    # The last is echo-only because phases intentionally do not overlap.
    items = collocate_events(events, echo, current)
    assert items[0].echo_active and not items[0].current_active
    assert not items[1].echo_active and items[1].current_active
    assert not items[2].echo_active and not items[2].current_active
    assert items[3].echo_active and not items[3].current_active
    assert items[1].echo_active is False  # event at prior echo end is excluded


def test_joint_counts_and_padding():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    windows = generate_windows(start, start + timedelta(hours=1), EchoSchedule(1800, 600), schedule_type="echo")
    event = sar_event("joint", start + timedelta(minutes=5))
    item = collocate_events([event], windows, windows, padding_seconds=360)[0]
    assert item.echo_active and item.current_active and item.joint_collocation
    assert item.padding_any_overlap and not item.padding_full_coverage
    assert 0 < item.padding_fraction_covered < 1
    counts = summarize_collocations([item])
    assert counts["total_joint_collocations"] == 1
