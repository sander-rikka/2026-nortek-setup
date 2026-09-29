from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import httpx

from sig500_campaign.models import iso_utc, parse_datetime

from .cache import FileCache
from .models import SarAcquisitionEvent

CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def _attributes(product: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in product.get("Attributes") or []:
        name = item.get("Name")
        if name:
            result[name.lower()] = item.get("Value")
    return result


def _name_details(name: str) -> tuple[str, str, str]:
    parts = name.split("_")
    platform = parts[0] if parts else "S1?"
    mode = parts[1] if len(parts) > 1 else ""
    product_type = parts[2] if len(parts) > 2 else ""
    return platform, mode, product_type


def products_to_events(products: list[dict[str, Any]]) -> list[SarAcquisitionEvent]:
    candidates: list[dict[str, Any]] = []
    for product in products:
        name = product.get("Name", "")
        platform, mode, product_type = _name_details(name)
        if mode not in {"IW", "EW"} or product_type.startswith(("AUX", "OCN")):
            continue
        content = product.get("ContentDate") or {}
        if not content.get("Start"):
            continue
        attrs = _attributes(product)
        orbit = attrs.get("relativeorbitnumber") or attrs.get("relativeorbit")
        direction = attrs.get("orbitdirection")
        datatake = attrs.get("datatakeid") or attrs.get("datatakeidentifier")
        start = parse_datetime(content["Start"])
        end = parse_datetime(content.get("End", content["Start"]))
        candidates.append(
            {
                "platform": platform,
                "mode": mode,
                "product_type": product_type,
                "product": product,
                "start": start,
                "end": end,
                "orbit": int(orbit) if orbit is not None else None,
                "direction": str(direction).upper() if direction else None,
                "datatake": str(datatake) if datatake else None,
            }
        )
    groups: list[list[dict[str, Any]]] = []
    for candidate in sorted(candidates, key=lambda item: (item["start"], item["platform"])):
        midpoint = candidate["start"] + (candidate["end"] - candidate["start"]) / 2
        match = None
        for group in reversed(groups):
            representative = group[0]["start"] + (group[0]["end"] - group[0]["start"]) / 2
            if (midpoint - representative).total_seconds() > 10:
                break
            first = group[0]
            same_metadata = (
                candidate["platform"] == first["platform"]
                and candidate["mode"] == first["mode"]
                and candidate["orbit"] == first["orbit"]
                and candidate["direction"] == first["direction"]
                and (
                    candidate["datatake"] is None
                    or first["datatake"] is None
                    or candidate["datatake"] == first["datatake"]
                )
            )
            if same_metadata and abs((midpoint - representative).total_seconds()) <= 10:
                match = group
                break
        if match is None:
            groups.append([candidate])
        else:
            match.append(candidate)
    events: list[SarAcquisitionEvent] = []
    for group in groups:
        group.sort(key=lambda item: (not item["product_type"].startswith("GRD"), item["product"].get("Name", "")))
        representative = group[0]
        platform = representative["platform"]
        mode = representative["mode"]
        orbit = representative["orbit"]
        direction = representative["direction"]
        datatake = next((item["datatake"] for item in group if item["datatake"]), None)
        start = min(item["start"] for item in group)
        end = max(item["end"] for item in group)
        key = (platform, start, end, orbit, direction, datatake, mode)
        names = tuple(sorted({item["product"].get("Name", "") for item in group if item["product"].get("Name")}))
        digest = hashlib.sha1("|".join(map(str, key)).encode()).hexdigest()[:12]
        events.append(
            SarAcquisitionEvent.from_interval(
                id=f"historical-{digest}",
                platform=platform,
                sensing_start_utc=start,
                sensing_end_utc=end,
                acquisition_mode=mode,
                orbit_direction=direction,
                relative_orbit=orbit,
                source="historical_actual",
                confidence="actual",
                source_product_names=names,
                datatake_id=datatake,
            )
        )
    return sorted(events, key=lambda event: event.representative_time_utc)


class CopernicusHistoricalProvider:
    def __init__(self, *, client: httpx.Client | None = None, cache: FileCache | None = None):
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)
        self.cache = cache

    def build_filter(self, lat: float, lon: float, start: datetime, end: datetime) -> str:
        return (
            "OData.CSC.Intersects(area=geography'SRID=4326;"
            f"POINT({lon} {lat})') and Collection/Name eq 'SENTINEL-1' and "
            f"ContentDate/Start ge {iso_utc(start)} and ContentDate/Start lt {iso_utc(end)}"
        )

    def fetch(
        self, lat: float, lon: float, start: datetime, end: datetime, *, refresh: bool = False
    ) -> list[SarAcquisitionEvent]:
        params = {"$filter": self.build_filter(lat, lon, start, end), "$expand": "Attributes", "$top": "1000"}
        cache_key = CATALOGUE_URL + "?" + params["$filter"]
        payload = None if refresh or not self.cache else self.cache.get_json(cache_key)
        try:
            if payload is None:
                products: list[dict[str, Any]] = []
                url: str | None = CATALOGUE_URL
                query: dict[str, str] | None = params
                while url:
                    response = self.client.get(url, params=query)
                    response.raise_for_status()
                    page = response.json()
                    products.extend(page.get("value", []))
                    url = page.get("@odata.nextLink")
                    query = None
                payload = products
                if self.cache:
                    self.cache.set_json(cache_key, payload)
        except (httpx.HTTPError, ValueError) as exc:
            cached = self.cache.get_json(cache_key) if self.cache else None
            if cached is None:
                raise RuntimeError(f"Copernicus catalogue unavailable and no cache exists: {exc}") from exc
            payload = cached
        return products_to_events(payload)
