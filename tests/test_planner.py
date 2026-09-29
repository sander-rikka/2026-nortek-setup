from datetime import datetime, timedelta, timezone

from conftest import sar_event
from sig500_campaign.models import Campaign
from sig500_campaign.nortek.deploy_parser import parse_deploy
from sig500_campaign.planner import generate_campaign


def test_full_offline_generation_and_clipped_override(tmp_path, reference_text):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    official = sar_event("official-edge", start + timedelta(seconds=5))
    official_centered = sar_event("official-center", start + timedelta(minutes=15))
    result = generate_campaign(
        campaign=Campaign(start, end, 30, 1.5, 59.5, 24.5),
        template=parse_deploy(reference_text),
        output_dir=tmp_path,
        echo_interval_seconds=1800,
        echo_duration_seconds=600,
        current_interval_seconds=900,
        current_duration_seconds=300,
        current_enabled=True,
        phase_resolution_seconds=1,
        padding_seconds=0,
        coverage_mode="point",
        historical_events=[],
        official_events=[official, official_centered],
        predicted_events=[],
        patterns=[],
        ensure_sentinel_coverage=True,
    )
    expected = {
        "optimized.deploy", "campaign_schedule.csv", "sar_acquisitions.csv", "sar_collocations.csv",
        "campaign_summary.json", "campaign_report.txt", "nortek_config_diff.txt",
    }
    assert expected == {path.name for path in tmp_path.iterdir()}
    summary = result["summary"]
    assert summary["echo_schedule"]["sample_rate_hz"] == 4.0
    assert summary["current_schedule"]["duration_seconds"] == 300
    assert summary["nortek"]["requested"]["SETAVG"]["NPING"] == 122
    assert summary["echo_schedule"]["extra_echo_windows"] == 1
    assert summary["echo_schedule"]["official_events_recovered"] == 1
    assert "optimized phase calculated but not written" in " ".join(summary["nortek"]["warnings"]).lower()
