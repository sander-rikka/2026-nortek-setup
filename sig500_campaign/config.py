from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


SECTIONS: dict[str, set[str]] = {
    "campaign": {
        "start",
        "end",
        "water_depth_m",
        "head_height_above_bottom_m",
        "lat",
        "lon",
        "surface_margin_m",
    },
    "nortek": {"template", "output_dir"},
    "echo": {"interval_min", "duration_min", "phase_resolution_sec"},
    "current": {"enabled", "interval_min", "duration_min"},
    "sentinel": {
        "padding_min",
        "collocation_coverage_mode",
        "lookback_days",
        "pattern_min_events",
        "pattern_max_mad_min",
        "refresh_data",
        "ensure_coverage",
        "allow_predicted_overrides",
    },
    "runtime": {"offline"},
}

REQUIRED_CAMPAIGN_FIELDS = {
    "start",
    "end",
    "water_depth_m",
    "head_height_above_bottom_m",
    "lat",
    "lon",
}

DEFAULTS: dict[str, Any] = {
    "surface_margin_m": 2.0,
    "template": "AD2CP_500kHz_108181_test2.deploy",
    "output_dir": ".",
    "echo_interval_min": 30.0,
    "echo_duration_min": 10.0,
    "phase_resolution_sec": 1,
    "current_enabled": True,
    "current_interval_min": None,
    "current_duration_min": None,
    "sentinel_padding_min": 0.0,
    "collocation_coverage_mode": "point",
    "sentinel_lookback_days": 730,
    "pattern_min_events": 3,
    "pattern_max_mad_min": 30.0,
    "refresh_sentinel_data": False,
    "ensure_sentinel_coverage": False,
    "allow_predicted_overrides": False,
    "offline": False,
}

FIELD_MAP = {
    ("campaign", "start"): "start",
    ("campaign", "end"): "end",
    ("campaign", "water_depth_m"): "water_depth_m",
    ("campaign", "head_height_above_bottom_m"): "head_height_above_bottom_m",
    ("campaign", "lat"): "lat",
    ("campaign", "lon"): "lon",
    ("campaign", "surface_margin_m"): "surface_margin_m",
    ("nortek", "template"): "template",
    ("nortek", "output_dir"): "output_dir",
    ("echo", "interval_min"): "echo_interval_min",
    ("echo", "duration_min"): "echo_duration_min",
    ("echo", "phase_resolution_sec"): "phase_resolution_sec",
    ("current", "enabled"): "current_enabled",
    ("current", "interval_min"): "current_interval_min",
    ("current", "duration_min"): "current_duration_min",
    ("sentinel", "padding_min"): "sentinel_padding_min",
    ("sentinel", "collocation_coverage_mode"): "collocation_coverage_mode",
    ("sentinel", "lookback_days"): "sentinel_lookback_days",
    ("sentinel", "pattern_min_events"): "pattern_min_events",
    ("sentinel", "pattern_max_mad_min"): "pattern_max_mad_min",
    ("sentinel", "refresh_data"): "refresh_sentinel_data",
    ("sentinel", "ensure_coverage"): "ensure_sentinel_coverage",
    ("sentinel", "allow_predicted_overrides"): "allow_predicted_overrides",
    ("runtime", "offline"): "offline",
}


def _read(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read configuration {path}: {exc}") from exc
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(text)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(text)
        else:
            raise ConfigError("configuration file must end in .json, .yaml, or .yml")
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid configuration syntax in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError("configuration root must be an object/mapping")
    return value


def load_config(path: Path) -> dict[str, Any]:
    raw = _read(path)
    unknown_sections = set(raw) - set(SECTIONS)
    if unknown_sections:
        raise ConfigError(f"unknown configuration section(s): {', '.join(sorted(unknown_sections))}")
    values = dict(DEFAULTS)
    for section, allowed_fields in SECTIONS.items():
        section_value = raw.get(section, {})
        if section_value is None:
            section_value = {}
        if not isinstance(section_value, dict):
            raise ConfigError(f"configuration section {section!r} must be a mapping")
        unknown_fields = set(section_value) - allowed_fields
        if unknown_fields:
            names = ", ".join(f"{section}.{field}" for field in sorted(unknown_fields))
            raise ConfigError(f"unknown configuration field(s): {names}")
        for field, value in section_value.items():
            values[FIELD_MAP[(section, field)]] = value
    campaign = raw.get("campaign") or {}
    missing = REQUIRED_CAMPAIGN_FIELDS - set(campaign)
    if missing:
        raise ConfigError(
            "missing required configuration field(s): "
            + ", ".join(f"campaign.{field}" for field in sorted(missing))
        )
    values["config_directory"] = path.resolve().parent
    return values


def resolve_config_path(value: str | Path, config_directory: Path | None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and config_directory is not None:
        path = config_directory / path
    return path.resolve()
