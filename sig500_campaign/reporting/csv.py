from __future__ import annotations

import csv
from pathlib import Path

from sig500_campaign.scheduling.collocations import Collocation
from sig500_campaign.scheduling.models import MeasurementWindow
from sig500_campaign.sentinel.models import SarAcquisitionEvent


def _write(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_campaign_schedule(path: Path, windows: list[MeasurementWindow]) -> None:
    fields = [
        "schedule_type", "window_number", "window_type", "start_utc", "end_utc",
        "duration_seconds", "interval_seconds", "sample_rate_hz", "samples", "sar_overlap", "sar_event_ids",
    ]
    _write(path, [window.as_dict() for window in windows], fields)


def write_sar_acquisitions(path: Path, events: list[SarAcquisitionEvent]) -> None:
    fields = [
        "id", "platform", "sensing_start_utc", "sensing_end_utc", "representative_time_utc",
        "acquisition_mode", "orbit_direction", "relative_orbit", "source", "confidence", "pattern_id",
        "source_product_names",
    ]
    rows = []
    for event in events:
        row = event.as_dict()
        row["source_product_names"] = ";".join(event.source_product_names)
        rows.append(row)
    _write(path, rows, fields)


def write_sar_collocations(path: Path, collocations: list[Collocation]) -> None:
    fields = [
        "sar_event_id", "acquisition_time_utc", "platform", "acquisition_mode", "relative_orbit",
        "orbit_direction", "sar_source", "sar_confidence", "pattern_id", "echo_active",
        "echo_window_number", "echo_window_start_utc", "echo_window_end_utc",
        "echo_offset_from_center_seconds", "echo_edge_margin_seconds", "current_active",
        "current_window_number", "current_window_start_utc", "current_window_end_utc", "joint_collocation",
        "padding_any_overlap", "padding_full_coverage", "padding_fraction_covered",
    ]
    _write(path, [item.as_dict() for item in collocations], fields)
