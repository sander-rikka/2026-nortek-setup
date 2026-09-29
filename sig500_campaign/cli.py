from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import typer

from sig500_campaign.config import ConfigError, DEFAULTS, load_config, resolve_config_path
from sig500_campaign.models import Campaign, parse_datetime
from sig500_campaign.nortek.deploy_parser import parse_deploy
from sig500_campaign.planner import generate_campaign
from sig500_campaign.sentinel.cache import FileCache
from sig500_campaign.sentinel.copernicus import CopernicusHistoricalProvider
from sig500_campaign.sentinel.esa_plan import ESAPlannedAcquisitionProvider
from sig500_campaign.sentinel.patterns import analyze_repeat_patterns
from sig500_campaign.sentinel.prediction import HistoricalRepeatPredictionProvider, merge_future_events

app = typer.Typer(add_completion=False, help="Plan Signature500 campaigns for Sentinel-1 collocations.")


def _seconds(minutes: float, name: str) -> int:
    value = minutes * 60
    if value != int(value):
        raise typer.BadParameter(f"{name} must resolve to whole seconds")
    return int(value)


@app.command()
def main(
    config: Path | None = typer.Option(None, exists=True, readable=True, help="JSON or YAML campaign configuration."),
    start: str | None = typer.Option(None, help="Campaign start ISO-8601 timestamp with timezone."),
    end: str | None = typer.Option(None, help="Campaign end ISO-8601 timestamp with timezone."),
    water_depth_m: float | None = typer.Option(None, min=0),
    head_height_above_bottom_m: float | None = typer.Option(None, min=0),
    lat: float | None = typer.Option(None, min=-90, max=90),
    lon: float | None = typer.Option(None, min=-180, max=180),
    template: Path | None = typer.Option(None, readable=True),
    output_dir: Path | None = typer.Option(None),
    surface_margin_m: float | None = typer.Option(None, min=0),
    echo_interval_min: float | None = typer.Option(None, min=0),
    echo_duration_min: float | None = typer.Option(None, min=0),
    current_interval_min: float | None = typer.Option(None, min=0),
    current_duration_min: float | None = typer.Option(None, min=0),
    current_enabled: bool | None = typer.Option(None, "--current-enabled/--no-current-enabled"),
    phase_resolution_sec: int | None = typer.Option(None, min=1),
    sentinel_padding_min: float | None = typer.Option(None, min=0),
    collocation_coverage_mode: str | None = typer.Option(None, help="point, any, or full"),
    sentinel_lookback_days: int | None = typer.Option(None, min=1),
    pattern_min_events: int | None = typer.Option(None, min=2),
    pattern_max_mad_min: float | None = typer.Option(None, min=0),
    refresh_sentinel_data: bool | None = typer.Option(None, "--refresh-sentinel-data/--no-refresh-sentinel-data"),
    ensure_sentinel_coverage: bool | None = typer.Option(None, "--ensure-sentinel-coverage/--no-ensure-sentinel-coverage"),
    allow_predicted_overrides: bool | None = typer.Option(None, "--allow-predicted-overrides/--no-allow-predicted-overrides"),
    offline: bool | None = typer.Option(None, "--offline/--online", help="Control Sentinel network access."),
) -> None:
    """Generate a candidate deploy file and campaign/SAR reports."""
    try:
        configured = load_config(config) if config else {**DEFAULTS, "config_directory": None}
    except ConfigError as exc:
        raise typer.BadParameter(str(exc), param_hint="--config") from exc

    def choose(cli_value, name):
        return cli_value if cli_value is not None else configured.get(name)

    start = choose(start, "start")
    end = choose(end, "end")
    water_depth_m = choose(water_depth_m, "water_depth_m")
    head_height_above_bottom_m = choose(head_height_above_bottom_m, "head_height_above_bottom_m")
    lat = choose(lat, "lat")
    lon = choose(lon, "lon")
    missing = [
        name
        for name, value in {
            "start": start,
            "end": end,
            "water_depth_m": water_depth_m,
            "head_height_above_bottom_m": head_height_above_bottom_m,
            "lat": lat,
            "lon": lon,
        }.items()
        if value is None
    ]
    if missing:
        raise typer.BadParameter(
            "provide --config or the required option(s): " + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )
    template_from_cli = template is not None
    output_from_cli = output_dir is not None
    template = resolve_config_path(
        choose(template, "template"), None if template_from_cli else configured["config_directory"]
    )
    output_dir = resolve_config_path(
        choose(output_dir, "output_dir"), None if output_from_cli else configured["config_directory"]
    )
    if not template.is_file():
        raise typer.BadParameter(f"template file does not exist: {template}", param_hint="--template")
    surface_margin_m = choose(surface_margin_m, "surface_margin_m")
    echo_interval_min = choose(echo_interval_min, "echo_interval_min")
    echo_duration_min = choose(echo_duration_min, "echo_duration_min")
    current_interval_min = choose(current_interval_min, "current_interval_min")
    current_duration_min = choose(current_duration_min, "current_duration_min")
    current_enabled = choose(current_enabled, "current_enabled")
    phase_resolution_sec = choose(phase_resolution_sec, "phase_resolution_sec")
    sentinel_padding_min = choose(sentinel_padding_min, "sentinel_padding_min")
    collocation_coverage_mode = choose(collocation_coverage_mode, "collocation_coverage_mode")
    sentinel_lookback_days = choose(sentinel_lookback_days, "sentinel_lookback_days")
    pattern_min_events = choose(pattern_min_events, "pattern_min_events")
    pattern_max_mad_min = choose(pattern_max_mad_min, "pattern_max_mad_min")
    refresh_sentinel_data = choose(refresh_sentinel_data, "refresh_sentinel_data")
    ensure_sentinel_coverage = choose(ensure_sentinel_coverage, "ensure_sentinel_coverage")
    allow_predicted_overrides = choose(allow_predicted_overrides, "allow_predicted_overrides")
    offline = choose(offline, "offline")
    campaign = Campaign(
        parse_datetime(str(start)), parse_datetime(str(end)), water_depth_m, head_height_above_bottom_m, lat, lon, surface_margin_m
    )
    if collocation_coverage_mode not in {"point", "any", "full"}:
        raise typer.BadParameter("must be point, any, or full", param_hint="--collocation-coverage-mode")
    echo_interval = _seconds(echo_interval_min, "echo interval")
    echo_duration = _seconds(echo_duration_min, "echo duration")
    current_interval = _seconds(current_interval_min, "current interval") if current_interval_min is not None else None
    current_duration = _seconds(current_duration_min, "current duration") if current_duration_min is not None else None
    cache = FileCache(output_dir / ".sentinel_cache")
    warnings: list[str] = []
    historical = []
    official = []
    if not offline:
        try:
            historical = CopernicusHistoricalProvider(cache=cache).fetch(
                lat, lon, campaign.start - timedelta(days=sentinel_lookback_days), campaign.start,
                refresh=refresh_sentinel_data,
            )
        except RuntimeError as exc:
            warnings.append(str(exc))
        try:
            official = ESAPlannedAcquisitionProvider(cache=cache).fetch(
                lat, lon, campaign.start, campaign.end, refresh=refresh_sentinel_data
            )
        except RuntimeError as exc:
            warnings.append(str(exc))
    else:
        warnings.append("Offline mode: Sentinel network retrieval skipped.")
    patterns = analyze_repeat_patterns(
        historical, min_events=pattern_min_events, max_mad_minutes=pattern_max_mad_min
    )
    coverage_end = max((event.representative_time_utc for event in official), default=None)
    predictions = HistoricalRepeatPredictionProvider().predict(
        patterns, campaign.start, campaign.end, official_coverage_end=coverage_end
    )
    merged = merge_future_events(official, predictions)
    predictions = [event for event in merged if event.source == "predicted_from_history"]
    result = generate_campaign(
        campaign=campaign,
        template=parse_deploy(template),
        output_dir=output_dir,
        echo_interval_seconds=echo_interval,
        echo_duration_seconds=echo_duration,
        current_interval_seconds=current_interval,
        current_duration_seconds=current_duration,
        current_enabled=current_enabled,
        phase_resolution_seconds=phase_resolution_sec,
        padding_seconds=sentinel_padding_min * 60,
        coverage_mode=collocation_coverage_mode,
        historical_events=historical,
        official_events=official,
        predicted_events=predictions,
        patterns=patterns,
        ensure_sentinel_coverage=ensure_sentinel_coverage,
        allow_predicted_overrides=allow_predicted_overrides,
        sentinel_warnings=warnings,
    )
    typer.echo(result["report"])


if __name__ == "__main__":
    app()
