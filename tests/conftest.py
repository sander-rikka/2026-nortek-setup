from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sig500_campaign.sentinel.models import SarAcquisitionEvent


REFERENCE_TEXT = (
    '#$InstrumentType="Signature500"\r\n'
    '#$Orientation="UP"\r\n'
    '#$Wrapped metadata begins\r\n'
    '#$ and continues unchanged\r\n'
    'SETDEFAULT\r\n'
    'SETPLAN,MIAVG=600,AVG=1,BURST=1,MIBURST=600,DIAVG=0,DIBURST=0,VENDORX=77\r\n'
    'SETAVG,AI=600,NPING=122,NB=4,NC=43,CS=0.5,BD=0.5,CY="ENU",VR=1\r\n'
    'SETBURST,SR=2,NS=1200,NB=1,CH=5,ECHO=1\r\n'
    'SETECHO,NC=3633,BINSIZE=0.006,BD=0.5,FREQ1=500,XMIT1=1,PL1=0,PULSECOMP1=1\r\n'
    'SETTMAVG,EN=0,AVG=60\r\n'
    'VENDORCOMMAND,FOO="bar baz",X=9 ; keep comment\r\n'
    'SAVE\r\n'
)


@pytest.fixture
def reference_text() -> str:
    return REFERENCE_TEXT


def sar_event(
    event_id: str,
    time: datetime,
    *,
    source: str = "official_plan",
    platform: str = "S1A",
    orbit: int = 87,
    direction: str = "ASCENDING",
    mode: str = "IW",
) -> SarAcquisitionEvent:
    return SarAcquisitionEvent.from_interval(
        id=event_id,
        platform=platform,
        sensing_start_utc=time,
        sensing_end_utc=time,
        acquisition_mode=mode,
        orbit_direction=direction,
        relative_orbit=orbit,
        source=source,
        confidence="official" if source == "official_plan" else "actual",
    )


@pytest.fixture
def utc():
    return timezone.utc
