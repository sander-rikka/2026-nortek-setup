from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx
from lxml import etree, html
from shapely.geometry import Point, Polygon

from .cache import FileCache
from .models import SarAcquisitionEvent

PLAN_PAGE = "https://sentinels.copernicus.eu/copernicus/sentinel-1/acquisition-plans"


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _metadata(placemark: etree._Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for data in placemark.xpath(".//*[local-name()='Data']"):
        name = data.get("name")
        values = data.xpath(".//*[local-name()='value']/text()")
        if name and values:
            result[_normal(name)] = values[0].strip()
    for simple in placemark.xpath(".//*[local-name()='SimpleData']"):
        name = simple.get("name")
        if name and simple.text:
            result[_normal(name)] = simple.text.strip()
    descriptions = placemark.xpath(".//*[local-name()='description']/text()")
    if descriptions:
        fragment = html.fromstring(f"<div>{descriptions[0]}</div>")
        cells = [" ".join(cell.itertext()).strip() for cell in fragment.xpath(".//td|.//th")]
        for index in range(0, len(cells) - 1, 2):
            result.setdefault(_normal(cells[index]), cells[index + 1])
        for key, value in re.findall(r"([A-Za-z][A-Za-z ]+)\s*[:=]\s*([^<\n]+)", descriptions[0]):
            result.setdefault(_normal(key), value.strip())
    return result


def _polygons(placemark: etree._Element) -> Iterable[Polygon]:
    for coordinates in placemark.xpath(".//*[local-name()='Polygon']//*[local-name()='coordinates']/text()"):
        points = []
        for coordinate in coordinates.split():
            pieces = coordinate.split(",")
            if len(pieces) >= 2:
                points.append((float(pieces[0]), float(pieces[1])))
        if len(points) >= 3:
            polygon = Polygon(points)
            if polygon.is_valid:
                yield polygon


def parse_plan_kml(data: bytes, *, lat: float, lon: float) -> list[SarAcquisitionEvent]:
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("KMZ contains no KML")
            data = archive.read(kml_names[0])
    root = etree.fromstring(data)
    point = Point(lon, lat)
    events: list[SarAcquisitionEvent] = []
    for placemark in root.xpath(".//*[local-name()='Placemark']"):
        if not any(polygon.covers(point) for polygon in _polygons(placemark)):
            continue
        metadata = _metadata(placemark)
        mode = metadata.get("mode", "").upper()
        if mode not in {"IW", "EW"}:
            continue
        start_raw = metadata.get("observationtimestart") or metadata.get("sensingstart") or metadata.get("start")
        end_raw = metadata.get("observationtimestop") or metadata.get("sensingstop") or metadata.get("stop")
        if not start_raw or not end_raw:
            continue
        start, end = _parse_time(start_raw), _parse_time(end_raw)
        platform = metadata.get("satelliteid") or metadata.get("platform") or "S1?"
        datatake = metadata.get("datatakeid")
        orbit = metadata.get("orbitrelative") or metadata.get("relativeorbit")
        direction = metadata.get("orbitdirection")
        identity = f"{platform}|{start.isoformat()}|{end.isoformat()}|{datatake or ''}"
        event_id = "official-" + hashlib.sha1(identity.encode()).hexdigest()[:12]
        events.append(
            SarAcquisitionEvent.from_interval(
                id=event_id,
                platform=platform,
                sensing_start_utc=start,
                sensing_end_utc=end,
                acquisition_mode=mode,
                orbit_direction=direction.upper() if direction else None,
                relative_orbit=int(orbit) if orbit else None,
                source="official_plan",
                confidence="official",
                source_product_names=(),
                datatake_id=datatake,
            )
        )
    return sorted(events, key=lambda item: item.representative_time_utc)


class ESAPlannedAcquisitionProvider:
    def __init__(self, *, client: httpx.Client | None = None, cache: FileCache | None = None):
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self.cache = cache

    def discover_plan_urls(self, *, refresh: bool = False) -> list[str]:
        cached = None if refresh or not self.cache else self.cache.get_bytes(PLAN_PAGE)
        try:
            if cached:
                page = cached
            else:
                response = self.client.get(PLAN_PAGE)
                response.raise_for_status()
                page = response.content
            if not cached and self.cache:
                self.cache.set_bytes(PLAN_PAGE, page)
        except httpx.HTTPError as exc:
            if cached is None:
                raise RuntimeError(f"ESA acquisition plan page unavailable: {exc}") from exc
            page = cached
        tree = html.fromstring(page)
        urls = []
        for href in tree.xpath("//a/@href"):
            normalized = href.lower().split("?")[0]
            if normalized.endswith((".kml", ".kmz")) or re.search(r"/s1[abcd]_mp_(?:user_)?\d{8}t\d{6}_\d{8}t\d{6}$", normalized):
                urls.append(str(httpx.URL(PLAN_PAGE).join(href)))
        return list(dict.fromkeys(urls))

    def fetch(
        self,
        lat: float,
        lon: float,
        start: datetime,
        end: datetime,
        *,
        urls: list[str] | None = None,
        refresh: bool = False,
    ) -> list[SarAcquisitionEvent]:
        events: list[SarAcquisitionEvent] = []
        candidates = urls or self.discover_plan_urls(refresh=refresh)
        relevant_urls = []
        for url in candidates:
            match = re.search(r"_(\d{8}t\d{6})_(\d{8}t\d{6})(?:\.[a-z]+)?$", url, re.IGNORECASE)
            if match:
                coverage_start = datetime.strptime(match.group(1).lower(), "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc)
                coverage_end = datetime.strptime(match.group(2).lower(), "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc)
                if coverage_end < start or coverage_start >= end:
                    continue
            relevant_urls.append(url)
        if urls is None:
            newest_by_platform: dict[str, str] = {}
            unclassified: list[str] = []
            for url in relevant_urls:
                platform_match = re.search(r"/(s1[abcd])_mp_", url, re.IGNORECASE)
                if platform_match:
                    newest_by_platform.setdefault(platform_match.group(1).upper(), url)
                else:
                    unclassified.append(url)
            relevant_urls = list(newest_by_platform.values()) + unclassified
        for url in relevant_urls:
            cached = None if refresh or not self.cache else self.cache.get_bytes(url)
            try:
                if cached:
                    content = cached
                else:
                    response = self.client.get(url)
                    response.raise_for_status()
                    content = response.content
                if not cached and self.cache:
                    self.cache.set_bytes(url, content)
            except httpx.HTTPError:
                if cached is None:
                    continue
                content = cached
            try:
                parsed = parse_plan_kml(content, lat=lat, lon=lon)
            except (ValueError, etree.XMLSyntaxError, zipfile.BadZipFile):
                continue
            events.extend(event for event in parsed if start <= event.representative_time_utc < end)
        unique = {event.id: event for event in events}
        return sorted(unique.values(), key=lambda item: item.representative_time_utc)
