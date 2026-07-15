"""Overpass API (OpenStreetMap) source — free, unlimited, no key."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..models import Lead

logger = logging.getLogger("empire-leads.overpass")

USER_AGENT = "EmpireLeads/0.1.0 (open-source lead discovery engine; founder@empire-ai.co.uk)"
API_URL = "https://overpass-api.de/api/interpreter"
TIMEOUT = 20

# OSM tag -> search query builder
# Format: (niche, tag_key, tag_value) — tag_value can be None for wildcard
BUSINESS_TAGS: list[tuple[str, str, str]] = [
    ("roofing",  "craft", "roofer"),
    ("roofing",  "craft", "roofing"),
    ("hvac",     "craft", "hvac_contractor"),
    ("hvac",     "craft", "air_conditioning"),
    ("plumbing", "craft", "plumber"),
    ("electrical", "craft", "electrician"),
    ("pest_control", "craft", "pest_control"),
    ("landscaping",  "craft", "landscaper"),
    ("solar",    "craft", "solar_installer"),
    # Solar installer fallback: most solar companies are tagged via shop or
    # office rather than craft, and 99% of solar companies also do roofing.
    ("solar",    "shop",  "solar"),
    ("solar",    "office", "energy_supplier"),
    ("legal",    "office", "lawyer"),
    ("legal",    "office", "notary"),
    ("legal",    "amenity", "lawyer"),
    ("general",  "shop",  "trade"),
]  # fmt: on

# Fallback: search OSM "shop" and "office" tags when craft doesn't match
FALLBACK_MAP = {
    "roofing":        "roofing",
    "hvac":           "heating, ventilation, air conditioning",
    "plumbing":       "plumber",
    "electrical":     "electrician",
}

# Major US metro areas with lat/lon for Overpass queries
METRO_AREAS = {
    "Phoenix, AZ":     (33.4484, -112.0740),
    "Dallas, TX":      (32.7767, -96.7970),
    "Houston, TX":     (29.7604, -95.3698),
    "Austin, TX":      (30.2672, -97.7431),
    "San Antonio, TX": (29.4241, -98.4936),
    "Los Angeles, CA": (34.0522, -118.2437),
    "San Diego, CA":   (32.7157, -117.1611),
    "Miami, FL":       (25.7617, -80.1918),
    "Orlando, FL":     (28.5383, -81.3792),
    "Tampa, FL":       (27.9506, -82.4572),
    "Atlanta, GA":     (33.7490, -84.3880),
    "Charlotte, NC":   (35.2271, -80.8431),
    "Raleigh, NC":     (35.7796, -78.6382),
    "Nashville, TN":   (36.1627, -86.7816),
    "Denver, CO":      (39.7392, -104.9903),
    "Seattle, WA":     (47.6062, -122.3321),
    "Portland, OR":    (45.5152, -122.6784),
    "Chicago, IL":     (41.8781, -87.6298),
    "New York, NY":    (40.7128, -74.0060),
    "Philadelphia, PA":(39.9526, -75.1652),
    "Las Vegas, NV":   (36.1699, -115.1398),
    "Phoenix2":        (33.4484, -112.0740),
}


def _build_query(
    tags: list[tuple[str, str]],
    lat: float,
    lon: float,
    radius_m: int,
) -> str:
    """Build an Overpass QL query for multiple tag pairs."""
    # Union of node/way/rel queries for each tag pair
    filters = []
    for key, val in tags:
        if val:
            filters.append(f'["{key}"="{val}"]')
        else:
            filters.append(f'["{key}"]')

    parts = []
    for filt in filters:
        parts.append(
            f'node{filt}(around:{radius_m},{lat},{lon});'
            f'way{filt}(around:{radius_m},{lat},{lon});'
            f'rel{filt}(around:{radius_m},{lat},{lon});'
        )

    union_body = "\n    ".join(parts)
    return f"""
    [out:json][timeout:{TIMEOUT}];
    (
      {union_body}
    );
    out body;
    """


def _query_overpass(query: str) -> dict:
    """Execute Overpass API query."""
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _element_to_lead(el: dict, niche: str) -> Optional[Lead]:
    """Convert an OSM element dict into a Lead."""
    tags = el.get("tags", {})
    name = (tags.get("name") or "").strip()
    if not name:
        return None

    # Extract address components
    city = (tags.get("addr:city") or tags.get("addr:suburb") or "").strip()
    state = (tags.get("addr:state") or "").strip()
    street = (tags.get("addr:housenumber") or "").strip()
    if street:
        street += " "
    street += (tags.get("addr:street") or "").strip()
    zip_code = (tags.get("addr:postcode") or "").strip()

    # Phone — normalize
    phone = (tags.get("phone") or "").strip()
    if not phone:
        phone = (tags.get("contact:phone") or "").strip()

    # Website
    website = (tags.get("website") or tags.get("contact:website") or "").strip()

    # Email
    email = (tags.get("email") or tags.get("contact:email") or "").strip()

    # Coordinates
    lat = el.get("lat")
    lon = el.get("lon")

    # Category
    category = (tags.get("craft") or tags.get("shop") or tags.get("office") or "").strip()

    return Lead(
        name=name[:200],
        source="overpass:osm",
        niche=niche,
        phone=phone[:30],
        website=website[:500],
        email=email[:200],
        address=f"{street}, {city}, {state} {zip_code}".strip(", ").strip(),
        city=city[:100],
        state=state[:50],
        zip_code=zip_code[:20],
        latitude=lat,
        longitude=lon,
        category=category[:100],
        raw={"osm_id": el.get("id"), "osm_type": el.get("type")},
    )


def discover(
    niche: str,
    near: str = "",
    radius_m: int = 20000,
    limit: int = 100,
    lat: float | None = None,
    lon: float | None = None,
) -> list[Lead]:
    """
    Discover businesses via Overpass API.

    Args:
        niche: Business type (roofing, hvac, plumbing, etc.)
        near: City/area name or "lat,lon"
        radius_m: Search radius in meters (default 20km)
        limit: Max results to return
        lat: Latitude override (if provided, lon must also be set)
        lon: Longitude override
    """
    # Resolve location
    if lat is not None and lon is not None:
        pass  # use provided coords
    else:
        lat, lon = _resolve_location(near)
    if lat is None:
        logger.warning("No location specified, using Phoenix, AZ")
        lat, lon = 33.4484, -112.0740

    # Build tag pairs for this niche
    tags = []
    for n, key, val in BUSINESS_TAGS:
        if n == niche:
            tags.append((key, val))
    if not tags:
        # Fallback: use the niche as a search term in name
        tags.append(("name", niche))
        tags.append(("description", niche))

    query = _build_query(tags[:3], lat, lon, radius_m)
    logger.debug("Overpass query:\n%s", query)

    try:
        result = _query_overpass(query)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        logger.error("Overpass query failed: %s", e)
        return []

    elements = result.get("elements", [])
    logger.info("Overpass returned %d raw elements", len(elements))

    leads: list[Lead] = []
    seen = set()
    for el in elements:
        lead = _element_to_lead(el, niche)
        if lead is None:
            continue
        # Dedup by name (OSM can return same business as node+way)
        key = lead.name.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        leads.append(lead)
        if len(leads) >= limit:
            break

    return leads


def _resolve_location(near: str) -> tuple[Optional[float], Optional[float]]:
    """Resolve 'Phoenix, AZ' or 'lat,lon' to coordinates."""
    near = near.strip()
    if not near:
        return None, None

    # Try "lat,lon" format
    if "," in near:
        try:
            parts = near.split(",")
            return float(parts[0].strip()), float(parts[1].strip())
        except (ValueError, IndexError):
            pass

    # Try known metro areas
    if near in METRO_AREAS:
        return METRO_AREAS[near]

    # Try partial match
    for name, coords in METRO_AREAS.items():
        if near.lower() in name.lower():
            return coords

    # Try Nominatim geocoding as last resort (rate-limited, free)
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(near)}&format=json&limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass

    return None, None
