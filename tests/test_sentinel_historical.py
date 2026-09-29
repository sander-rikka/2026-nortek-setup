from datetime import datetime, timezone

import httpx
import pytest

from sig500_campaign.sentinel.copernicus import CopernicusHistoricalProvider, products_to_events
from sig500_campaign.sentinel.cache import FileCache


def _product(name):
    return {
        "Name": name,
        "ContentDate": {"Start": "2026-01-01T00:00:00Z", "End": "2026-01-01T00:01:00Z"},
        "Attributes": [
            {"Name": "relativeOrbitNumber", "Value": 87},
            {"Name": "orbitDirection", "Value": "ASCENDING"},
            {"Name": "datatakeID", "Value": "ABC"},
        ],
    }


def test_grd_slc_dedup_and_mode_filtering():
    products = [
        _product("S1A_IW_GRDH_1SDV_x"), _product("S1A_IW_SLC__1SDV_x"),
        _product("S1A_SM_GRDH_1SDV_x"), _product("S1A_IW_AUX__x"),
    ]
    events = products_to_events(products)
    assert len(events) == 1
    assert len(events[0].source_product_names) == 2
    assert events[0].acquisition_mode == "IW"


def test_subsecond_product_timestamps_are_same_overpass():
    first = _product("S1A_IW_GRDH_1SDV_x")
    second = _product("S1A_IW_SLC__1SDV_x")
    second["ContentDate"] = {"Start": "2026-01-01T00:00:00.500Z", "End": "2026-01-01T00:01:00.500Z"}
    events = products_to_events([first, second])
    assert len(events) == 1
    assert len(events[0].source_product_names) == 2


def test_query_uses_lon_lat():
    provider = CopernicusHistoricalProvider()
    value = provider.build_filter(59.5, 24.5, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert "POINT(24.5 59.5)" in value


def test_network_failure_is_explicit():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)
    provider = CopernicusHistoricalProvider(client=httpx.Client(transport=httpx.MockTransport(fail)))
    with pytest.raises(RuntimeError, match="no cache"):
        provider.fetch(59.5, 24.5, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc))


def test_cache_used_after_network_failure(tmp_path):
    payload = {"value": [_product("S1A_IW_GRDH_1SDV_x")]}

    def success(request):
        return httpx.Response(200, json=payload, request=request)

    cache = FileCache(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    first = CopernicusHistoricalProvider(client=httpx.Client(transport=httpx.MockTransport(success)), cache=cache)
    assert len(first.fetch(59.5, 24.5, start, end)) == 1

    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    second = CopernicusHistoricalProvider(client=httpx.Client(transport=httpx.MockTransport(fail)), cache=cache)
    assert len(second.fetch(59.5, 24.5, start, end)) == 1
