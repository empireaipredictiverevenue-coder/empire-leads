"""Google Places source — optional enrichment when API key available.

Requires GOOGLE_MAPS_API_KEY env var. Silently returns empty when absent.
Ref: warehouse-sniper/sniper.py Google Places textSearch.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from ..models import Lead

log = logging.getLogger(__name__)

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
USER_AGENT = "EmpireLeads/0.1.0 (founder@empire-ai.co.uk)"

# Place search queries per niche
NICHE_QUERIES: dict[str, list[str]] = {
    "roofing": ["roofing contractor", "roofing company", "roofer"],
    "hvac": ["hvac contractor", "hvac company", "heating and cooling"],
    "plumbing": ["plumber", "plumbing contractor", "plumbing company"],
    "electrical": ["electrician", "electrical contractor"],
    "solar": ["solar installer", "solar company"],
    "landscaping": ["landscaper", "landscaping company"],
    "pest_control": ["pest control", "exterminator"],
    "cleaning": ["cleaning service", "janitorial service"],
}


def discover(
    niche: str,
    lat: float,
    lon: float,
    radius_m: int = 8000,
    max_results: int = 20,
) -> list[Lead]:
    """Search Google Places for businesses in a niche near a location.

    Args:
        niche: Target niche.
        lat, lon: Center point.
        radius_m: Search radius in meters.
        max_results: Max leads to return.

    Returns:
        List of Lead objects. Empty if no API key configured.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        log.info("[Google] No GOOGLE_MAPS_API_KEY — skipping")
        return []

    queries = NICHE_QUERIES.get(niche, [niche])
    leads: list[Lead] = []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.location,places.nationalPhoneNumber,places.websiteUri,"
            "places.businessStatus,places.types,places.rating,places.userRatingCount"
        ),
    }

    seen_ids: set[str] = set()

    for query in queries:
        body = json.dumps({
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": radius_m,
                }
            },
            "maxResultCount": 10,
        }).encode()

        try:
            req = urllib.request.Request(
                PLACES_URL, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            log.warning(f"[Google] {query} failed: {e}")
            continue

        for p in data.get("places", []):
            pid = p.get("id", "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            loc = p.get("location", {})
            addr = p.get("formattedAddress", "")
            leads.append(Lead(
                name=p.get("displayName", {}).get("text", "Unknown"),
                source="google_places",
                niche=niche,
                phone=p.get("nationalPhoneNumber"),
                website=p.get("websiteUri"),
                address=addr,
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
                rating=p.get("rating") or 0.0,
                category=", ".join(p.get("types", [])),
                raw={
                    "place_id": pid,
                    "business_status": p.get("businessStatus"),
                    "user_rating_count": p.get("userRatingCount"),
                },
            ))

            if len(leads) >= max_results:
                break

        if len(leads) >= max_results:
            break

    log.info(f"[Google] {len(leads)} leads from Places API")
    return leads
