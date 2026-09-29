from sig500_campaign.nortek.deploy_parser import parse_deploy
from sig500_campaign.nortek.deploy_patcher import patch_timing
from sig500_campaign.nortek.validation import echo_end_range_m


def _default(document):
    return patch_timing(
        document,
        echo_interval_seconds=1800,
        echo_duration_seconds=600,
        current_enabled=True,
        current_interval_seconds=1800,
        current_duration_seconds=600,
    )


def test_default_patch_changes_only_intended_fields(reference_text):
    original = parse_deploy(reference_text)
    result = _default(original)
    changed = {change.path for change in result.changes if change.changed}
    assert changed == {"SETPLAN.MIAVG", "SETPLAN.MIBURST", "SETBURST.SR", "SETBURST.NS"}
    assert result.document.get("SETAVG", "AI") == 600
    assert result.document.get("SETAVG", "NPING") == 122
    assert result.document.get("SETPLAN", "VENDORX") == 77
    assert result.document.get("SETTMAVG", "AVG") == 60
    assert 'FOO="bar baz"' in result.document.text
    assert result.document.newline == "\r\n"


def test_changed_ai_requires_instrument_validation(reference_text):
    result = patch_timing(
        parse_deploy(reference_text), echo_interval_seconds=1800, echo_duration_seconds=600,
        current_enabled=True, current_interval_seconds=900, current_duration_seconds=300,
    )
    assert result.document.get("SETAVG", "AI") == 300
    assert result.document.get("SETAVG", "NPING") == 122
    assert any("REQUIRES_INSTRUMENT_LIMIT_VALIDATION" in warning for warning in result.warnings)


def test_echo_range_from_template(reference_text):
    assert echo_end_range_m(parse_deploy(reference_text)) == 22.298
