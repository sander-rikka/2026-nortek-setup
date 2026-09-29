from __future__ import annotations

from sig500_campaign.scheduling.collocations import Collocation


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def render_report(summary: dict, collocations: list[Collocation]) -> str:
    campaign = summary["campaign"]
    geometry = summary["geometry"]
    echo = summary["echo_schedule"]
    current = summary["current_schedule"]
    counts = summary["sentinel"]["collocations"]
    nortek = summary["nortek"]
    lines = [
        "Campaign", "--------",
        f"Start:                     {campaign['start']}",
        f"End:                       {campaign['end']}",
        f"Water depth:               {campaign['water_depth_m']:.1f} m",
        f"ADCP head above bottom:    {campaign['head_height_above_bottom_m']:.1f} m",
        f"Head depth:                {geometry['head_depth_below_surface_m']:.1f} m",
        "", "Echosounder", "-----------",
        f"Sampling rate:             {echo['sample_rate_hz']:.3f} Hz",
        f"Active duration:           {echo['duration_seconds']} s",
        f"Measurement interval:      {echo['interval_seconds']} s",
        f"Samples/window:            {echo['samples_per_full_window']}",
        f"Duty cycle:                {echo['duty_cycle']:.2%}",
        f"Optimized phase:           {echo['phase_seconds']} s",
        f"Configured echo end range: {geometry['configured_echo_end_range_m']:.3f} m",
        f"Transducer-to-surface:     {geometry['estimated_transducer_to_surface_distance_m']:.3f} m",
        f"Selected surface margin:   {geometry['surface_margin_m']:.3f} m",
        f"Unmeasured near-surface:   {geometry['estimated_unmeasured_near_surface_distance_m']:.3f} m",
        "", "Average currents", "----------------",
        f"Active averaging interval: {current['duration_seconds']} s",
        f"Measurement interval:      {current['interval_seconds']} s",
        f"NPING:                     {nortek['requested'].get('SETAVG', {}).get('NPING', 'unknown')}",
        f"Schedule inherited from echo: {'YES' if current['inherited_from_echo'] else 'NO'}",
        "", "SAR forecast", "------------",
        f"Expected SAR acquisitions:          {counts['total_sar_acquisitions_during_deployment']}",
        f"Expected echo collocations:         {counts['total_echo_collocations']}",
        f"Expected current collocations:      {counts['total_current_collocations']}",
        f"Expected joint collocations:        {counts['total_joint_collocations']}",
        f"Official planned:                   {counts['official_planned_acquisitions']}",
        f"Predicted from clear pattern:       {counts['predicted_acquisitions']}",
        f"Echo acquisition coverage:          {counts['echo_collocation_fraction']:.1%}",
        "", "Future collocations", "-------------------",
        "UTC                  Platform Mode Orbit Source       Echo Current Joint",
    ]
    for item in collocations:
        orbit = f"R{item.relative_orbit:03d}" if item.relative_orbit is not None else "-"
        source = "official" if item.sar_source == "official_plan" else "predicted"
        lines.append(
            f"{item.acquisition_time_utc:%Y-%m-%d %H:%M}  {item.platform:<8} {item.acquisition_mode:<4} "
            f"{orbit:<5} {source:<12} {_yes(item.echo_active):<5} {_yes(item.current_active):<7} {_yes(item.joint_collocation)}"
        )
        if item.echo_active:
            lines.append(
                f"  echo {item.echo_window_start_utc.isoformat()} to {item.echo_window_end_utc.isoformat()}; "
                f"center offset {item.echo_offset_from_center_seconds:.1f}s; edge margin {item.echo_edge_margin_seconds:.1f}s"
            )
        if item.current_active:
            lines.append(
                f"  current {item.current_window_start_utc.isoformat()} to {item.current_window_end_utc.isoformat()}"
            )
    lines.extend(["", "Nortek changes", "--------------"])
    for path, values in nortek["diff"].items():
        if values["changed"]:
            lines.append(f"{path:<24} {values['original']} -> {values['requested']}")
    lines.append("Unchanged:")
    for path, values in nortek["diff"].items():
        if not values["changed"]:
            lines.append(f"{path:<24} {values['original']}")
    lines.extend(
        [
            "", "Validation", "----------",
            "Candidate .deploy generated.",
            "Physical-instrument / Signature Deployment validation still required.",
            "Use GETPLANLIM, GETAVGLIM, GETBURSTLIM, GETECHOLIM, SAVE, GETERROR, and READCFG where supported.",
            "Future SAR acquisitions are expectations rather than guarantees. Official acquisition plans may change,",
            "and historically inferred recurrence does not guarantee acquisition.",
        ]
    )
    lines.extend(f"WARNING: {warning}" for warning in nortek["warnings"])
    lines.extend(f"WARNING: {warning}" for warning in summary["sentinel"]["warnings"])
    return "\n".join(lines) + "\n"
