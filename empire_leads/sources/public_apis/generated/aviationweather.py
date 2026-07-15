"""Auto-generated source from public-apis catalog.

API:        AviationWeather
Description:NOAA aviation weather forecasts and observations
Category:   Weather
Auth:       No
HTTPS:      True
CORS:       Unknown
Docs:       https://www.aviationweather.gov/dataserver

This is a v1 STUB. It hits the docs URL and tries to parse JSON.
Many public-api "docs" pages return HTML, in which case this
source returns []. To make it real:
  1. Read the docs at: https://www.aviationweather.gov/dataserver
  2. Replace the `_fetch()` body with the real endpoint + params
  3. Map the response fields into Lead() in `_to_lead()`
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ....models import Lead

logger = logging.getLogger("empire-leads.public_apis.aviationweather")

API_URL = "https://www.aviationweather.gov/dataserver"
TIMEOUT = 15
USER_AGENT = "EmpireLeads/0.1 (public-apis source; founder@empire-ai.co.uk)"


def _fetch(limit: int = 20) -> list[dict]:
    """GET the docs URL (v1 stub). Returns parsed JSON list, or []."""
    try:
        req = urllib.request.Request(
            API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.info("[aviationweather] docs URL returned non-JSON (HTML?) — stub returns []")
            return []
        if isinstance(data, list):
            return data[:limit]
        if isinstance(data, dict):
            # common: {"results": [...]} or {"data": [...]} or {"items": [...]}
            for k in ("results", "data", "items", "records", "entries"):
                if k in data and isinstance(data[k], list):
                    return data[k][:limit]
            return [data]  # single object
        return []
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("[aviationweather] fetch failed: %s", e)
        return []


def _to_lead(item: dict, niche: str) -> Lead:
    """Map a single API response item to a Lead. v1 best-effort."""
    name = (
        item.get("name")
        or item.get("title")
        or item.get("company")
        or item.get("business_name")
        or "AviationWeather"
    )
    return Lead(
        name=str(name)[:200],
        source="public_apis:aviationweather",
        niche=niche,
        phone=str(item.get("phone") or item.get("telephone") or ""),
        website=str(item.get("url") or item.get("website") or item.get("link") or ""),
        email=str(item.get("email") or ""),
        address=str(item.get("address") or item.get("location") or ""),
        city=str(item.get("city") or ""),
        state=str(item.get("state") or item.get("region") or ""),
        zip_code=str(item.get("zip") or item.get("postal_code") or ""),
        latitude=item.get("lat") or item.get("latitude"),
        longitude=item.get("lon") or item.get("lng") or item.get("longitude"),
        rating=item.get("rating"),
        category=str(item.get("category") or "Weather"),
        about=str(item.get("description") or "")[:500],
        raw=item,
    )


def discover(niche: str = "general", limit: int = 20, **kwargs) -> list[Lead]:
    """v1 stub: hit docs URL, parse JSON if possible."""
    items = _fetch(limit=limit)
    return [_to_lead(it, niche) for it in items]
