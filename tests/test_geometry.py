import pytest

from sig500_campaign.geometry import adcp_slanted_beam_geometry, vertical_echo_geometry


def test_head_height_and_margin():
    result = vertical_echo_geometry(30, 1.5, 2)
    assert result.head_depth_below_surface_m == 28.5
    assert result.usable_vertical_range_m == 26.5
    assert "not derived" in adcp_slanted_beam_geometry(30, 1.5).note


@pytest.mark.parametrize("depth,height,margin", [(0, 0, 0), (30, -1, 2), (30, 30, 2), (30, 29, 2)])
def test_invalid_geometry(depth, height, margin):
    with pytest.raises(ValueError):
        vertical_echo_geometry(depth, height, margin)
