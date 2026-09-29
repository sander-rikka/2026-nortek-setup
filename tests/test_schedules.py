from datetime import datetime, timezone

import pytest

from sig500_campaign.scheduling.currents import resolve_current_schedule
from sig500_campaign.scheduling.models import CurrentSchedule, EchoSchedule, generate_windows


def test_echo_invariant_and_samples():
    assert EchoSchedule(1800, 600).samples_per_window == 2400
    with pytest.raises(ValueError):
        EchoSchedule(1800, 600, sample_rate_hz=2)


def test_current_inheritance_and_override():
    echo = EchoSchedule(1800, 600, 317)
    inherited = resolve_current_schedule(echo, None, None)
    assert (inherited.interval_seconds, inherited.duration_seconds, inherited.phase_seconds) == (1800, 600, 317)
    assert inherited.inherited_from_echo
    explicit = resolve_current_schedule(echo, 900, 300)
    assert (explicit.interval_seconds, explicit.duration_seconds, explicit.phase_seconds) == (900, 300, 0)
    assert not explicit.inherited_from_echo


def test_separate_schedule_validation_and_independence():
    with pytest.raises(ValueError):
        CurrentSchedule(300, 301)
    echo = EchoSchedule(1800, 600)
    current = CurrentSchedule(900, 300)
    assert echo.duration_seconds != current.duration_seconds


def test_campaign_end_exclusive_and_clipping():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start.replace(hour=1)
    windows = generate_windows(start, end, EchoSchedule(1800, 600, 1700), schedule_type="echo")
    assert windows[0].start == start.replace(minute=28, second=20)
    assert windows[-1].end == end
    assert all(window.start < end for window in windows)
