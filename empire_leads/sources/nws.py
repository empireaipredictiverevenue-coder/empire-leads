"""NWS storm source — severe weather alerts as lead triggers.

Free, no API key. Uses api.weather.gov/alerts/active.
Ref: warehouse-sniper/sniper.py + Empire-USA-Strike/striker_agent.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import urllib.request
import urllib.error

from ..models import Lead

log = logging.getLogger(__name__)

NWS_URL = "https://api.weather.gov/alerts/active"
USER_AGENT = "EmpireLeads/0.1.0 (founder@empire-ai.co.uk)"

# Storm events that trigger lead generation for contractor services
STORM_TRIGGERS = {
    "TORNADO", "SEVERE THUNDERSTORM", "HAIL", "FLASH FLOOD",
    "FLOOD WARNING", "HURRICANE", "TROPICAL STORM", "WIND",
}

SEVERITY_ALLOWLIST = {"Severe", "Extreme"}

# Niche mapping — storm type → likely contractor niches
STORM_NICHE_MAP: dict[str, list[str]] = {
    "TORNADO":           ["roofing", "contractor", "general_contractor"],
    "SEVERE THUNDERSTORM": ["roofing", "hvac"],
    "HAIL":              ["roofing", "solar", "hvac"],
    "FLASH FLOOD":       ["plumbing", "contractor", "water_damage"],
    "FLOOD WARNING":     ["plumbing", "water_damage", "contractor"],
    "HURRICANE":         ["roofing", "contractor", "general_contractor", "solar"],
    "TROPICAL STORM":    ["roofing", "contractor"],
    "WIND":              ["roofing", "solar", "tree_service"],
}


def discover(
    state_filter: Optional[str] = None,
    max_alerts: int = 20,
    min_lead_score: int = 5,
) -> list[Lead]:
    """Fetch active NWS storm alerts and convert to leads.

    Args:
        state_filter: Optional 2-letter state code (e.g. "TX", "FL").
        max_alerts: Max alerts to process.
        min_lead_score: Minimum lead score threshold.

    Returns:
        List of Lead objects for storm-active zones.
    """
    # Build URL with optional filters
    params = ["status=actual", "message_type=alert"]
    url = f"{NWS_URL}?{'&'.join(params)}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        log.warning(f"[NWS] API fetch failed: {e}")
        return []

    features = data.get("features", [])
    leads: list[Lead] = []

    for feat in features:
        props = feat.get("properties", {})
        event = (props.get("event") or "").upper()
        severity = props.get("severity", "")
        area_desc = props.get("areaDesc", "")
        headline = props.get("headline", "")
        alert_id = props.get("id", feat.get("id", ""))

        # Severity filter
        if severity not in SEVERITY_ALLOWLIST:
            continue

        # Event filter
        trigger = None
        for t in STORM_TRIGGERS:
            if t in event:
                trigger = t
                break
        if not trigger:
            continue

        # Optional state filter
        if state_filter:
            parts = [p.strip() for p in area_desc.split(";")]
            if not any(state_filter.upper() in p for p in parts):
                continue

        # Extract polygon centroid for location
        centroid_lat, centroid_lon = None, None
        geom = feat.get("geometry")
        if geom and geom.get("type") == "Polygon":
            outer = (geom.get("coordinates") or [[]])[0]
            if outer:
                centroid_lon = sum(c[0] for c in outer) / len(outer)
                centroid_lat = sum(c[1] for c in outer) / len(outer)

        # Extract area name for location string
        area_parts = [p.strip() for p in area_desc.split(";") if p.strip()]
        # Last element is usually the state code
        location = area_desc[:100] if area_desc else headline[:100]

        # Determine target niches from storm type
        niches = STORM_NICHE_MAP.get(trigger, ["contractor"])

        lead_score = min(len(leads) + 1, 20)  # simple score

        leads.append(Lead(
            name=headline or f"Storm alert: {event}",
            source="nws",
            niche=niches[0] if niches else "contractor",
            about=f"{event} warning - {headline}\nAffected: {area_desc[:200]}",
            address=location,
            state=state_filter.upper() if state_filter else None,
            latitude=centroid_lat,
            longitude=centroid_lon,
            rating=lead_score,
            raw={
                "alert_id": alert_id,
                "event": event,
                "severity": severity,
                "trigger": trigger,
                "niches": niches,
                "expires": props.get("expires"),
                "sender": props.get("senderName"),
            },
        ))

        if len(leads) >= max_alerts:
            break

    log.info(f"[NWS] {len(leads)} storm-triggered leads" +
             (f" in {state_filter}" if state_filter else ""))
    return leads
