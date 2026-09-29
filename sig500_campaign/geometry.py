from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class VerticalEchoGeometry:
    water_depth_m: float
    head_height_above_bottom_m: float
    head_depth_below_surface_m: float
    surface_margin_m: float
    usable_vertical_range_m: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdcpSlantedBeamGeometry:
    head_depth_below_surface_m: float
    note: str = "ADCP slanted-beam profiling range is not derived in version 1."

    def as_dict(self) -> dict:
        return asdict(self)


def vertical_echo_geometry(
    water_depth_m: float,
    head_height_above_bottom_m: float,
    surface_margin_m: float = 2.0,
) -> VerticalEchoGeometry:
    if water_depth_m <= 0:
        raise ValueError("water_depth_m must be positive")
    if head_height_above_bottom_m < 0:
        raise ValueError("head_height_above_bottom_m must be non-negative")
    if head_height_above_bottom_m >= water_depth_m:
        raise ValueError("head_height_above_bottom_m must be less than water_depth_m")
    if surface_margin_m < 0:
        raise ValueError("surface_margin_m must be non-negative")
    head_depth = water_depth_m - head_height_above_bottom_m
    usable_range = head_depth - surface_margin_m
    if usable_range <= 0:
        raise ValueError("vertical usable range must be positive")
    return VerticalEchoGeometry(
        water_depth_m,
        head_height_above_bottom_m,
        head_depth,
        surface_margin_m,
        usable_range,
    )


def adcp_slanted_beam_geometry(
    water_depth_m: float, head_height_above_bottom_m: float
) -> AdcpSlantedBeamGeometry:
    geometry = vertical_echo_geometry(water_depth_m, head_height_above_bottom_m, 0)
    return AdcpSlantedBeamGeometry(geometry.head_depth_below_surface_m)
