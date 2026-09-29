from __future__ import annotations

import json

import pytest
import yaml
from typer.testing import CliRunner

from sig500_campaign.cli import app
from sig500_campaign.config import ConfigError, load_config, resolve_config_path


def _config() -> dict:
    return {
        "campaign": {
            "start": "2026-10-01T00:00:00Z",
            "end": "2026-10-01T02:00:00Z",
            "water_depth_m": 30,
            "head_height_above_bottom_m": 1.5,
            "lat": 59.5,
            "lon": 24.5,
        },
        "nortek": {"template": "reference.deploy", "output_dir": "output"},
        "echo": {"interval_min": 30, "duration_min": 10},
        "current": {"enabled": True, "interval_min": None, "duration_min": None},
        "runtime": {"offline": True},
    }


@pytest.mark.parametrize("suffix", [".yaml", ".yml", ".json"])
def test_load_json_and_yaml(tmp_path, suffix):
    path = tmp_path / f"campaign{suffix}"
    data = _config()
    path.write_text(json.dumps(data) if suffix == ".json" else yaml.safe_dump(data))
    values = load_config(path)
    assert values["echo_interval_min"] == 30
    assert values["current_interval_min"] is None
    assert values["offline"] is True
    assert resolve_config_path(values["template"], values["config_directory"]) == tmp_path / "reference.deploy"


def test_unknown_field_and_missing_required_are_rejected(tmp_path):
    data = _config()
    data["echo"]["duraton_min"] = 10
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="echo.duraton_min"):
        load_config(path)
    data = _config()
    del data["campaign"]["lat"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match="campaign.lat"):
        load_config(path)


def test_config_only_cli_run_and_override(tmp_path, reference_text):
    (tmp_path / "reference.deploy").write_text(reference_text, newline="")
    config_path = tmp_path / "campaign.yaml"
    config_path.write_text(yaml.safe_dump(_config()))
    result = CliRunner().invoke(app, ["--config", str(config_path), "--echo-duration-min", "5"])
    assert result.exit_code == 0, result.output
    output = tmp_path / "output"
    assert (output / "optimized.deploy").is_file()
    assert (output / "campaign_summary.json").is_file()
    summary = json.loads((output / "campaign_summary.json").read_text())
    assert summary["echo_schedule"]["duration_seconds"] == 300
    assert summary["current_schedule"]["duration_seconds"] == 300
    assert summary["current_schedule"]["inherited_from_echo"] is True
