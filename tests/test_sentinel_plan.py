from datetime import datetime, timezone

import httpx

from sig500_campaign.sentinel.esa_plan import ESAPlannedAcquisitionProvider, parse_plan_kml


KML = b'''<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
<ExtendedData>
<Data name="Satellite ID"><value>S1C</value></Data><Data name="DatatakeId"><value>6AD4</value></Data>
<Data name="Mode"><value>IW</value></Data>
<Data name="ObservationTimeStart"><value>2026-10-04T05:16:00Z</value></Data>
<Data name="ObservationTimeStop"><value>2026-10-04T05:18:00Z</value></Data>
<Data name="OrbitRelative"><value>87</value></Data></ExtendedData>
<Polygon><outerBoundaryIs><LinearRing><coordinates>
24,59 25,59 25,60 24,60 24,59
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''


def test_kml_point_in_polygon_and_official_provenance():
    inside = parse_plan_kml(KML, lat=59.5, lon=24.5)
    outside = parse_plan_kml(KML, lat=58, lon=24.5)
    assert len(inside) == 1 and not outside
    assert inside[0].source == "official_plan"
    assert inside[0].confidence == "official"
    assert inside[0].representative_time_utc == datetime(2026, 10, 4, 5, 17, tzinfo=timezone.utc)


def test_live_style_extensionless_plan_links_are_discovered():
    page = b'<html><a href="/documents/d/sentinel/s1c_mp_user_20260925t173103_20261017t194000">plan</a></html>'

    def handler(request):
        return httpx.Response(200, content=page, request=request)

    provider = ESAPlannedAcquisitionProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    urls = provider.discover_plan_urls()
    assert urls == ["https://sentinels.copernicus.eu/documents/d/sentinel/s1c_mp_user_20260925t173103_20261017t194000"]
