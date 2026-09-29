# sig500_campaign

`sig500_campaign` is a Python 3.11+ planning tool for bottom-mounted, fixed-frame,
upward-looking Nortek Signature500 deployments. It generates a minimally patched
Nortek candidate configuration and independent Average-current and
Burst/Echosounder schedules optimized for Sentinel-1 SAR collocations.

## Installation

```bash
uv sync --dev
uv run python -m sig500_campaign.cli --help
```

## Basic campaign

### Provide your own Nortek reference file

This repository does not distribute a Nortek `.deploy` reference file. Before
running a campaign, obtain or export a configuration for **your own** Signature500
using Nortek Signature Deployment, a configuration previously validated for your
instrument, or another Nortek-supported workflow. Do not invent missing commands
or copy an unrelated instrument configuration blindly.

Keep the reference file locally, for example as
`my_signature500_reference.deploy`, and set `nortek.template` to that path. All
`.deploy` files are ignored by this repository to reduce the risk of publishing
instrument identifiers, deployment metadata, local paths, operational settings,
or manufacturer-generated content unintentionally.

A `.deploy` reference may be published only when you have confirmed that:

- you or your organization have the right to redistribute it;
- applicable Nortek terms and institutional policies permit publication;
- instrument serial numbers, deployment locations, operator details, paths, and
  other sensitive metadata have been removed;
- it is clearly labelled as an example, not a universally valid Signature500
  configuration.

The safest public-repository approach is to omit real `.deploy` files and let
each user provide their own. The project license applies to this project's source
code and documentation; it does not automatically grant redistribution rights
for third-party or instrument-generated configuration files.

### Run from one configuration file

Edit `campaign.yaml`, including its `nortek.template` value, then run the entire
campaign from that one file:

```bash
uv run python -m sig500_campaign.cli --config campaign.yaml
```

Both `.yaml`/`.yml` and `.json` are supported. Relative `template` and
`output_dir` paths are resolved relative to the configuration file, not the
shell's working directory. Unknown sections and fields are rejected so that a
misspelled scientific setting does not silently fall back to a default.

The equivalent YAML structure is:

```yaml
campaign:
  start: "2026-10-01T00:00:00Z"
  end: "2026-11-01T00:00:00Z"
  water_depth_m: 30
  head_height_above_bottom_m: 1.5
  lat: 59.5
  lon: 24.5
  surface_margin_m: 2
nortek:
  template: my_signature500_reference.deploy
  output_dir: campaign_output
echo:
  interval_min: 30
  duration_min: 10
  phase_resolution_sec: 1
current:
  enabled: true
  interval_min: null  # inherit echo timing
  duration_min: null  # inherit echo timing
sentinel:
  padding_min: 0
  collocation_coverage_mode: point
  lookback_days: 730
  pattern_min_events: 3
  pattern_max_mad_min: 30
  refresh_data: false
  ensure_coverage: false
  allow_predicted_overrides: false
runtime:
  offline: false
```

Individual CLI options remain available as explicit overrides. For example,
`--config campaign.yaml --offline` uses the file but disables network access for
that run.

The longer option-only form remains supported for automation:

```bash
uv run python -m sig500_campaign.cli \
  --start 2026-10-01T00:00:00Z \
  --end 2026-11-01T00:00:00Z \
  --water-depth-m 30 \
  --head-height-above-bottom-m 1.5 \
  --lat 59.5 --lon 24.5 \
  --echo-interval-min 30 --echo-duration-min 10 \
  --template my_signature500_reference.deploy
```

Add `--offline` for deterministic operation without catalogue or plan downloads.
The command writes `optimized.deploy`, `campaign_schedule.csv`,
`sar_acquisitions.csv`, `sar_collocations.csv`, `campaign_summary.json`,
`campaign_report.txt`, and `nortek_config_diff.txt`.

## Independent measurement schedules

The echosounder is an extension of Burst mode. It follows the Burst schedule; it
does not have an independent third timer:

- Echo/Burst timer: `SETPLAN.MIBURST` + `SETBURST.SR` + `SETBURST.NS`.
- Average-current timer: `SETPLAN.MIAVG` + `SETAVG.AI`.

The echosounder sampling rate is a hard invariant of exactly 4 Hz. Average mode
is **not** forced to 4 Hz: `AI` is its active averaging interval, while `NPING`
and measurement-load settings govern internal pings. The program never claims
to know individual Average-mode ping times.

If current timing is omitted, it inherits echo interval, duration, and logical
phase. Use `--current-interval-min 15 --current-duration-min 5` for a separate
schedule. Use `--no-current-enabled` to disable Average mode. Arbitrary phase
offsets are not written to `DIAVG` or `DIBURST`: their semantics have not been
verified here. The report therefore gives a recommended logical echo phase and
warns that it was not encoded in the candidate `.deploy` file.

## Sentinel-1 data

Historical actual acquisitions come from the official [Copernicus Data Space
OData catalogue](https://documentation.dataspace.copernicus.eu/APIs/OData.html).
Queries use `POINT(longitude latitude)`, restrict the collection to Sentinel-1,
and retain IW/EW SAR acquisitions. GRD/SLC/RAW products for the same sensing
event are deduplicated; GRD is preferred as representative metadata while every
product name remains as provenance.

Future official acquisitions come from ESA's [Sentinel-1 acquisition-plan
KML/KMZ files](https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans).
Only planned datatake polygons containing the deployment point count. Downloaded
catalogue responses and plan files are cached in `.sentinel_cache`; use
`--refresh-sentinel-data` to refresh them.

If plans do not cover the full campaign, actual history is grouped by platform,
relative orbit, orbit direction, and mode. Median recurrence and median absolute
deviation (MAD) are calculated independently. Only clear patterns meeting
`--pattern-min-events` and `--pattern-max-mad-min` create explicitly labelled
`predicted_from_history` events. Predictions are expectations, never “planned”;
official events supersede nearby matching predictions.

## Acquisitions and collocations

- **SAR acquisition**: an official planned or historically inferred sensing event.
- **Echo collocation**: representative SAR time is in an active Burst/Echo window.
- **Current collocation**: SAR time is in an Average-current averaging window.
- **Joint collocation**: echo and current windows are both active.

Representative time is normally the midpoint of sensing start and end. Windows
are half-open: an event at the start is covered and one at the end is not.
`--sentinel-padding-min` adds an interval objective with `point`, `any`, or `full`
coverage modes. `--ensure-sentinel-coverage` can add exceptional echo-only
windows around uncovered official events; predicted overrides require the
separate `--allow-predicted-overrides` switch.

## Optimization, geometry, storage, and power

The phase search protects official acquisitions first, then maximizes total
coverage, maximizes minimum edge margin, minimizes total center offset, and uses
the smallest phase as deterministic tie-breaker. Schedules are clipped to the
half-open campaign interval.

With water depth `H` and head height above bottom `h`, nominal head depth is
`H-h`; the first-order vertical echo target is `H-h-surface_margin`. This is not
used for slanted ADCP beams. Acoustic `SETECHO` fields remain unchanged in v1.
Configured echo end range is diagnosed as `BD + NC*BINSIZE`.

Reports distinguish 4 Hz echo samples from configured `NPING` per Average
interval. Active-window fractions are not battery estimates. The report only
states burst-active-time reduction relative to continuous operation; absolute
battery lifetime is not estimated without a validated Nortek power model.

## Deploy-file handling

The parser retains original lines and patches only documented requested fields.
Metadata, wrapping, comments, quoted values, unknown commands, unknown fields,
ordering, and line endings are preserved where practical. Potentially stale
Signature Deployment-generated metadata is retained and flagged rather than
fabricated. `SETTMAVG` is telemetry averaging and is not silently synchronized
with primary Average mode. If `SETAVG.AI` changes, `NPING` and load-related
settings remain untouched and the candidate is marked
`REQUIRES_INSTRUMENT_LIMIT_VALIDATION`.

## Required instrument validation

Unit tests establish software behavior, **not** Signature500 compatibility.
Treat `optimized.deploy` only as a candidate:

1. Open/upload it in Nortek Signature Deployment or the supported terminal flow.
2. Connect the physical Signature500.
3. Where firmware supports them, query `GETPLANLIM`, `GETAVGLIM`, `GETBURSTLIM`,
   and `GETECHOLIM`.
4. `SAVE` and inspect validation errors; use `GETERROR` if `SAVE` fails.
5. Run `READCFG` and inspect the complete sampling-slot table.
6. Verify Average timing, Burst timing, echo slots, actual 4 Hz behavior, profile
   ranges, memory, and the instrument's power estimate.
7. Perform a short test deployment and inspect the resulting `.ad2cp` data before
   field deployment.

Official Nortek documentation and firmware-specific guidance should be checked
through the [Nortek Support Center](https://support.nortekgroup.com/).

## Known limitations

- v1 preserves rather than automatically tunes echosounder acoustics or ADCP range.
- Logical optimized phase is not written without verified Nortek offset semantics.
- ESA page structure and KML metadata can change; network failures degrade to
  cache or a warning, and offline campaigns contain no forecast unless events are
  supplied programmatically.
- Future plans can change and regular historical acquisition does not guarantee a
  future datatake.
