"""Carrier DRP roster scraper — insurance contractor directories."""
from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from typing import Any
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

TIMEOUT = 15
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

CARRIERS: dict[str, dict[str, Any]] = {
    "statefarm": {
        "name": "State Farm",
        "url": "https://claims.statefarm.com/find-contractor",
        "type": "web",
    },
    "allstate": {
        "name": "Allstate",
        "url": "https://www.allstate.com/claims/repair-center-locator.aspx",
        "type": "web",
    },
    "farmers": {
        "name": "Farmers",
        "url": "https://www.farmers.com/claims/repair-network/",
        "type": "web",
    },
    "liberty_mutual": {
        "name": "Liberty Mutual",
        "url": "https://www.libertymutual.com/claims/repair-network",
        "type": "web",
    },
    "nationwide": {
        "name": "Nationwide",
        "url": "https://www.nationwide.com/personal/claims/repair-network",
        "type": "web",
    },
    "travelers": {
        "name": "Travelers",
        "url": "https://www.travelers.com/claims/repair-network",
        "type": "web",
    },
    "progressive": {
        "name": "Progressive",
        "url": "https://www.progressive.com/claims/repair-network",
        "type": "web",
    },
    "usaa": {
        "name": "USAA",
        "url": "https://www.usaa.com/inet/ent_claims/RepairNetwork",
        "type": "web",
    },
}


@dataclass
class CarrierLead:
    """A contractor found on a carrier's approved roster."""
    carrier: str
    carrier_name: str
    company: str
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    url: str = ""
    specializations: list[str] = field(default_factory=list)
    license_number: str = ""


def _fetch(url: str) -> str | None:
    """Fetch a URL with browser-like headers."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning("[Carrier] %s — fetch failed: %s", url, e)
        return None


def _search_statefarm(zip_code: str = "85001") -> list[CarrierLead]:
    """Search State Farm contractor finder."""
    url = f"https://claims.statefarm.com/api/contractors/search?zip={zip_code}"
    html = _fetch(url)
    if not html:
        return []
    leads: list[CarrierLead] = []
    # Try JSON API first
    try:
        data = json.loads(html)
        for c in data if isinstance(data, list) else data.get("contractors", []):
            leads.append(CarrierLead(
                carrier="statefarm",
                carrier_name="State Farm",
                company=c.get("businessName", ""),
                phone=c.get("phone", ""),
                city=c.get("city", ""),
                state=c.get("state", ""),
                zip=c.get("zip", ""),
                specializations=c.get("services", []),
            ))
        if leads:
            return leads
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: HTML parse
    names = re.findall(r'businessName["\']?\s*[:=]\s*["\']([^"\']+)', html)
    phones = re.findall(r'phone["\']?\s*[:=]\s*["\']([^"\']+)', html)
    for i, name in enumerate(names):
        leads.append(CarrierLead(
            carrier="statefarm",
            carrier_name="State Farm",
            company=name,
            phone=phones[i] if i < len(phones) else "",
        ))
    return leads


def _scrape_allstate(near: str = "Phoenix, AZ") -> list[CarrierLead]:
    """Scrape Allstate repair center locator."""
    html = _fetch(CARRIERS["allstate"]["url"])
    if not html:
        return []
    leads: list[CarrierLead] = []
    names = re.findall(
        r'<h[23][^>]*>([^<]+(?:Roofing|Construction|Contractor|Restoration)[^<]*)',
        html, re.I,
    )
    cities = re.findall(r'(?:City|Location)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)', html)
    for i, name in enumerate(names[:20]):
        leads.append(CarrierLead(
            carrier="allstate",
            carrier_name="Allstate",
            company=name.strip(),
            city=cities[i] if i < len(cities) else near.split(",")[0].strip(),
        ))
    return leads


def _search_zips(carrier_key: str, zip_list: list[str]) -> list[CarrierLead]:
    """Search a carrier by iterating ZIP codes."""
    leads: list[CarrierLead] = []
    funcs = {
        "statefarm": _search_statefarm,
        "allstate": _scrape_allstate,
    }
    fn = funcs.get(carrier_key)
    if not fn:
        return leads
    for zip_code in zip_list:
        try:
            result = fn(zip_code)
            leads.extend(result)
        except Exception as e:
            log.warning("[Carrier] %s ZIP %s error: %s", carrier_key, zip_code, e)
    return leads


def discover(
    niche: str = "",
    near: str = "Phoenix, AZ",
    carriers: list[str] | None = None,
    zip_codes: list[str] | None = None,
    limit: int = 50,
) -> list[CarrierLead]:
    """Discover carrier-approved contractors.

    Args:
        niche: Not used for carriers (all specializations included).
        near: Metro area hint for ZIP resolution.
        carriers: List of carrier keys (default: all).
        zip_codes: ZIP codes to search (default: Phoenix metro).
        limit: Max results.

    Returns:
        List of CarrierLead dataclass instances.
    """
    from .overpass import _geocode_near
    active = [k for k in (carriers or list(CARRIERS.keys())) if k in CARRIERS]
    if not active:
        log.warning("[Carrier] No valid carriers in %s", carriers)
        return []

    if not zip_codes:
        coords = _geocode_near(near)
        if coords:
            lat, lon = coords
            zip_codes = [f"{int(lat):.0f}{int(lon):.0f}"]
        if not zip_codes:
            zip_codes = ["85001", "85002", "85003", "85004", "85006"]

    leads: list[CarrierLead] = []
    for ck in active:
        try:
            result = _search_zips(ck, zip_codes[:3])
            leads.extend(result)
        except Exception as e:
            log.warning("[Carrier] %s error: %s", ck, e)

    seen: set[tuple[str, str]] = set()
    deduped: list[CarrierLead] = []
    for l in leads:
        key = (l.carrier, l.company.lower().strip())
        if key not in seen:
            seen.add(key)
            deduped.append(l)

    log.info(
        "[Carrier] %d leads from %d carriers (after dedup)",
        len(deduped), len(active),
    )
    return deduped[:limit]
