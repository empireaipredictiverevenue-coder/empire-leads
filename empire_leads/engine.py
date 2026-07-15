"""Engine — multi-source lead discovery orchestrator."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from .models import Lead, ScanResult
from .sources import (overpass_discover, reddit_discover, nws_discover,
                       google_discover, carrier_discover,
                       state_license_discover)

log = logging.getLogger(__name__)

SOURCES: dict[str, Callable] = {
    "overpass": overpass_discover,
    "reddit": reddit_discover,
    "nws": nws_discover,
    "google_places": google_discover,
    "carrier_rosters": carrier_discover,
    "state_licenses": state_license_discover,
}

SOURCE_DESCRIPTIONS = {
    "overpass": "OpenStreetMap/Overpass — free, unlimited business listings",
    "reddit": "Reddit no-API — buying-intent signals from niche subreddits",
    "nws": "NWS storm alerts — severe weather as lead triggers",
    "google_places": "Google Places API — enrichment (requires GOOGLE_MAPS_API_KEY)",
    "carrier_rosters": "Insurance DRP contractor directories",
    "state_licenses": "State contractor license DBs (TX/GA/OH scrapable)",
}


def list_sources() -> dict:
    return {k: SOURCE_DESCRIPTIONS[k] for k in SOURCES}


def _contractor_to_lead(c, niche: str) -> "Lead":
    """Convert a ContractorForApplication to a Lead for unified output."""
    return Lead(
        name=c.company,
        source=f"carrier:{c.source}",
        niche=niche,
        phone=c.phone,
        address=c.address,
        city=c.city,
        state=c.state,
        zip_code=c.zip_code,
        latitude=c.latitude,
        longitude=c.longitude,
        about=f"License state: {c.license_state}; Carrier DRP candidate",
    )


def _license_to_lead(c, niche: str) -> "Lead":
    """Convert a LicensedContractor to a Lead."""
    about_parts = []
    if c.license_number:
        about_parts.append(f"License: {c.license_number}")
    if c.license_class:
        about_parts.append(f"Class: {c.license_class}")
    if c.expiration_date:
        about_parts.append(f"Expires: {c.expiration_date}")
    return Lead(
        name=c.name or c.company,
        source=f"license_db:{c.source}",
        niche=niche,
        phone=c.phone,
        address=c.address,
        city=c.city,
        state=c.state,
        zip_code=c.zip,
        latitude=c.latitude,
        longitude=c.longitude,
        category=c.license_class or "",
        about="; ".join(about_parts),
    )


def discover(
    niche: str,
    near: Optional[str] = None,
    *,
    sources: Optional[list[str]] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    state: Optional[str] = None,
    limit_per_source: int = 20,
    **kwargs,
) -> ScanResult:
    """Run lead discovery across multiple sources.

    Args:
        niche: Target niche (roofing, hvac, plumbing, etc.).
        near: City/area name (for geo sources).
        sources: List of source names. None = all.
        lat/lon: Manual coordinate override.
        state: State filter (for NWS).
        limit_per_source: Max leads per source.

    Returns:
        ScanResult with merged, deduped leads.
    """
    active_sources = sources if sources is not None else ["overpass"]
    start = time.time()

    leads: list[Lead] = []
    results = {}

    for name in active_sources:
        if name not in SOURCES:
            log.warning(f"Unknown source: {name}")
            continue

        fn = SOURCES[name]
        source_start = time.time()

        try:
            if name == "overpass":
                result = fn(niche, near=near or "", lat=lat, lon=lon,
                            radius_m=kwargs.get("radius_m", 20000), limit=limit_per_source)
            elif name == "reddit":
                result = fn(niche, limit=limit_per_source)
            elif name == "nws":
                result = fn(state_filter=state, max_alerts=limit_per_source)
            elif name == "google_places":
                if lat is None or lon is None:
                    log.info(f"[{name}] Skipping — no lat/lon")
                    continue
                result = fn(niche, lat=lat, lon=lon, max_results=limit_per_source)
            elif name == "carrier_rosters":
                # carrier returns ContractorForApplication; convert to Lead
                result = fn(niche=niche, near=near or "", limit=limit_per_source)
                result = [_contractor_to_lead(c, niche) for c in result]
            elif name == "state_licenses":
                result = fn(niche=niche, near=near or "", state=state or "TX",
                            limit=limit_per_source)
                result = [_license_to_lead(c, niche) for c in result]
            else:
                result = fn(niche, limit=limit_per_source)

            elapsed = time.time() - source_start
            results[name] = {"leads": len(result), "time_s": round(elapsed, 1)}
            leads.extend(result)

        except Exception as e:
            elapsed = time.time() - source_start
            log.warning(f"[{name}] Error after {elapsed:.1f}s: {e}")
            results[name] = {"leads": 0, "time_s": round(elapsed, 1), "error": str(e)}

    total_time = time.time() - start

    # Dedup by name (case-insensitive)
    seen_names: set[str] = set()
    deduped: list[Lead] = []
    for lead in leads:
        key = (lead.name or "").strip().lower()
        if key and key not in seen_names:
            seen_names.add(key)
            deduped.append(lead)
        elif not key:
            deduped.append(lead)

    return ScanResult(
        source=f"multi:{','.join(active_sources)}",
        niche=niche,
        leads=deduped,
        total_found=len(leads),
        total_deduped=len(deduped),
        time_s=round(total_time, 1),
        results=results,
    )
