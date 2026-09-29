from sig500_campaign.nortek.deploy_parser import parse_deploy


def test_reference_values_and_metadata(reference_text):
    document = parse_deploy(reference_text)
    assert document.instrument_type == "Signature500"
    assert document.orientation == "UP"
    assert document.get("SETPLAN", "MIAVG") == 600
    assert document.get("SETPLAN", "MIBURST") == 600
    assert document.get("SETAVG", "AI") == 600
    assert document.get("SETAVG", "NPING") == 122
    assert document.get("SETBURST", "SR") == 2
    assert document.get("SETBURST", "NS") == 1200
    assert document.get("SETBURST", "ECHO") == 1
    assert document.get("SETECHO", "NC") == 3633
    assert document.get("SETECHO", "BINSIZE") == 0.006
    assert len(document.metadata_lines) == 4


def test_unknown_and_quoted_values_preserved(reference_text):
    document = parse_deploy(reference_text)
    assert document.get("SETPLAN", "VENDORX") == 77
    assert document.get("VENDORCOMMAND", "FOO") == "bar baz"
    assert 'FOO="bar baz"' in document.text
    assert "; keep comment" in document.text
