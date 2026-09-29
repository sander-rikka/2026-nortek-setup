from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from sig500_campaign.geometry import vertical_echo_geometry
from sig500_campaign.models import Campaign, iso_utc
from sig500_campaign.nortek.deploy_parser import DeployDocument
from sig500_campaign.nortek.deploy_patcher import patch_timing
from sig500_campaign.nortek.diff import format_diff
from sig500_campaign.nortek.validation import compare_reference, echo_end_range_m
from sig500_campaign.reporting import (
    render_report,
    write_campaign_schedule,
    write_sar_acquisitions,
    write_sar_collocations,
    write_summary,
)
from sig500_campaign.scheduling.collocations import collocate_events, summarize_collocations
from sig500_campaign.scheduling.currents import resolve_current_schedule
from sig500_campaign.scheduling.models import EchoSchedule, MeasurementWindow, generate_windows
from sig500_campaign.scheduling.optimizer import optimize_echo_phase
from sig500_campaign.sentinel.models import SarAcquisitionEvent
from sig500_campaign.sentinel.patterns import RepeatPattern


def _active_seconds(windows: list[MeasurementWindow]) -> float:
    if not windows:
        return 0.0
    intervals = sorted((window.start, window.end) for window in windows)
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum((end - start).total_seconds() for start, end in merged)


def _annotate(windows: list[MeasurementWindow], events: list[SarAcquisitionEvent]) -> list[MeasurementWindow]:
    result = []
    for window in windows:
        ids = tuple(event.id for event in events if window.start <= event.representative_time_utc < window.end)
        result.append(replace(window, sar_event_ids=ids))
    return result


def _add_overrides(
    windows: list[MeasurementWindow],
    events: list[SarAcquisitionEvent],
    duration_seconds: int,
    campaign_start,
    campaign_end,
    *,
    allow_predicted: bool,
) -> tuple[list[MeasurementWindow], int, int, int]:
    added = 0
    official_recovered = 0
    predicted_recovered = 0
    result = list(windows)
    for event in events:
        already = any(window.start <= event.representative_time_utc < window.end for window in result)
        permitted = event.source == "official_plan" or (allow_predicted and event.source == "predicted_from_history")
        if already or not permitted:
            continue
        nominal_start = event.representative_time_utc - timedelta(seconds=duration_seconds / 2)
        nominal_end = nominal_start + timedelta(seconds=duration_seconds)
        start = max(nominal_start, campaign_start)
        end = min(nominal_end, campaign_end)
        clipped_duration = (end - start).total_seconds()
        result.append(
            MeasurementWindow("echo", len(result) + 1, "sentinel_override", start, end, clipped_duration, None, 4.0, int(clipped_duration * 4), (event.id,))
        )
        added += 1
        official_recovered += event.source == "official_plan"
        predicted_recovered += event.source == "predicted_from_history"
    result.sort(key=lambda window: window.start)
    result = [replace(window, window_number=index + 1) for index, window in enumerate(result)]
    return result, added, official_recovered, predicted_recovered


def generate_campaign(
    *,
    campaign: Campaign,
    template: DeployDocument,
    output_dir: Path,
    echo_interval_seconds: int,
    echo_duration_seconds: int,
    current_interval_seconds: int | None,
    current_duration_seconds: int | None,
    current_enabled: bool,
    phase_resolution_seconds: int,
    padding_seconds: float,
    coverage_mode: str,
    historical_events: list[SarAcquisitionEvent],
    official_events: list[SarAcquisitionEvent],
    predicted_events: list[SarAcquisitionEvent],
    patterns: list[RepeatPattern],
    ensure_sentinel_coverage: bool = False,
    allow_predicted_overrides: bool = False,
    sentinel_warnings: list[str] | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    future_events = sorted(official_events + predicted_events, key=lambda event: event.representative_time_utc)
    optimization = optimize_echo_phase(
        campaign.start,
        future_events,
        interval_seconds=echo_interval_seconds,
        duration_seconds=echo_duration_seconds,
        resolution_seconds=phase_resolution_seconds,
        padding_seconds=padding_seconds,
        coverage_mode=coverage_mode,
    )
    echo_schedule = optimization.schedule
    current_schedule = resolve_current_schedule(
        echo_schedule, current_interval_seconds, current_duration_seconds, enabled=current_enabled
    )
    echo_windows = generate_windows(campaign.start, campaign.end, echo_schedule, schedule_type="echo")
    baseline_active = _active_seconds(echo_windows)
    extra_count = official_recovered = predicted_recovered = 0
    if ensure_sentinel_coverage:
        echo_windows, extra_count, official_recovered, predicted_recovered = _add_overrides(
            echo_windows,
            future_events,
            echo_duration_seconds,
            campaign.start,
            campaign.end,
            allow_predicted=allow_predicted_overrides,
        )
    current_windows = generate_windows(campaign.start, campaign.end, current_schedule, schedule_type="current")
    echo_windows = _annotate(echo_windows, future_events)
    current_windows = _annotate(current_windows, future_events)
    collocations = collocate_events(future_events, echo_windows, current_windows, padding_seconds=padding_seconds)
    counts = summarize_collocations(collocations)
    patch = patch_timing(
        template,
        echo_interval_seconds=echo_interval_seconds,
        echo_duration_seconds=echo_duration_seconds,
        current_enabled=current_enabled,
        current_interval_seconds=current_schedule.interval_seconds,
        current_duration_seconds=current_schedule.duration_seconds,
    )
    geometry = vertical_echo_geometry(
        campaign.water_depth_m, campaign.head_height_above_bottom_m, campaign.surface_margin_m
    )
    configured_range = echo_end_range_m(template)
    campaign_seconds = (campaign.end - campaign.start).total_seconds()
    echo_active = _active_seconds(echo_windows)
    current_active = _active_seconds(current_windows)
    joint_seconds = _active_seconds(
        [
            MeasurementWindow("joint", index + 1, "periodic", max(e.start, c.start), min(e.end, c.end),
                              (min(e.end, c.end) - max(e.start, c.start)).total_seconds(), None, None, None)
            for index, (e, c) in enumerate(
                (pair for pair in ((e, c) for e in echo_windows for c in current_windows) if max(pair[0].start, pair[1].start) < min(pair[0].end, pair[1].end))
            )
        ]
    )
    original = template.relevant_settings()
    requested = patch.document.relevant_settings()
    diff = {
        change.path: {"original": change.original, "requested": change.requested, "changed": change.changed}
        for change in patch.changes
    }
    summary = {
        "campaign": campaign.as_dict(),
        "geometry": {
            **geometry.as_dict(),
            "configured_echo_end_range_m": configured_range,
            "estimated_transducer_to_surface_distance_m": geometry.head_depth_below_surface_m,
            "estimated_unmeasured_near_surface_distance_m": max(0.0, geometry.head_depth_below_surface_m - configured_range),
        },
        "nortek": {
            "original": original,
            "requested": requested,
            "diff": diff,
            "reference_comparison": compare_reference(template),
            "warnings": list(patch.warnings),
        },
        "echo_schedule": {
            **echo_schedule.as_dict(),
            "samples_per_full_window": echo_schedule.samples_per_window,
            "recommended_phase_seconds": echo_schedule.phase_seconds,
            "recommended_first_echo_window_utc": iso_utc(echo_windows[0].start) if echo_windows else None,
            "echo_active_seconds": echo_active,
            "echo_total_seconds": campaign_seconds,
            "duty_cycle": echo_active / campaign_seconds,
            "baseline_duty_cycle": baseline_active / campaign_seconds,
            "echo_sample_count": sum(window.samples or 0 for window in echo_windows),
            "number_of_echo_bursts": len(echo_windows),
            "extra_echo_windows": extra_count,
            "official_events_recovered": official_recovered,
            "predicted_events_recovered": predicted_recovered,
            "burst_active_time_reduction_vs_continuous": 1 - echo_active / campaign_seconds,
            "absolute_battery_lifetime": "not estimated",
        },
        "current_schedule": {
            **current_schedule.as_dict(),
            "current_active_seconds": current_active,
            "current_total_seconds": campaign_seconds,
            "current_active_fraction": current_active / campaign_seconds,
            "configured_nping_per_averaging_interval": requested.get("SETAVG", {}).get("NPING"),
        },
        "joint": {"overlap_seconds": joint_seconds},
        "sentinel": {
            "historical_acquisitions": [event.as_dict() for event in historical_events],
            "repeat_patterns": [pattern.as_dict() for pattern in patterns],
            "official_future_acquisitions": [event.as_dict() for event in official_events],
            "predicted_future_acquisitions": [event.as_dict() for event in predicted_events],
            "future_acquisitions": [event.as_dict() for event in future_events],
            "collocations": counts,
            "warnings": sentinel_warnings or [],
        },
    }
    (output_dir / "optimized.deploy").write_text(patch.document.text, encoding="utf-8", newline="")
    (output_dir / "nortek_config_diff.txt").write_text(format_diff(patch.changes), encoding="utf-8")
    write_campaign_schedule(output_dir / "campaign_schedule.csv", echo_windows + current_windows)
    write_sar_acquisitions(output_dir / "sar_acquisitions.csv", historical_events + future_events)
    write_sar_collocations(output_dir / "sar_collocations.csv", collocations)
    write_summary(output_dir / "campaign_summary.json", summary)
    report = render_report(summary, collocations)
    (output_dir / "campaign_report.txt").write_text(report, encoding="utf-8")
    return {"summary": summary, "report": report, "collocations": collocations}
