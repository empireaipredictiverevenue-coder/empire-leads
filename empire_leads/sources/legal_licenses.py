"""Attorney + legal service source — state bar records + Overpass.

State bar registries expose bar numbers (sourced from published attorney
directories; the registries' search endpoints often return captchas).
For unblockable results, we use:
1. OSM `office=lawyer` & `amenity=lawyer` for businesses
2. State bar lookup URLs (catalogued) for the application surface
3. Practice area classification from the company name
"""
from __future__ import annotations

import logging
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)


# US state bar associations — public attorney search endpoints
STATE_BARS: dict[str, dict[str, str]] = {
    "CA": {
        "name": "State Bar of California",
        "search": "https://apps.calbar.ca.gov/attorney/LicenseeSearch/QuickSearch",
        "bar_number_format": r"^\d{4,8}$",
    },
    "NY": {
        "name": "New York State Bar",
        "search": "https://iapps.courts.state.ny.us/attorney/AttorneySearch",
        "bar_number_format": r"^[A-Z]?\d{4,8}$",
    },
    "FL": {
        "name": "The Florida Bar",
        "search": "https://www.floridabar.org/the-florida-bar/find-a-member/",
        "bar_number_format": r"^\d{4,8}$",
    },
    "TX": {
        "name": "State Bar of Texas",
        "search": "https://www.texasbar.com/AM/Template.cfm?Section=Find_Lawyer",
        "bar_number_format": r"^\d{4,8}$",
    },
    "IL": {
        "name": "Illinois ARDC",
        "search": "https://www.iardc.org/LawyerSearch",
        "bar_number_format": r"^\d{4,8}$",
    },
    "PA": {
        "name": "Pennsylvania Disciplinary Board",
        "search": "https://www.padisciplinaryboard.org/attorney-search",
        "bar_number_format": r"^\d{4,8}$",
    },
    "GA": {
        "name": "State Bar of Georgia",
        "search": "https://www.gabar.org/membership/find-a-lawyer/",
        "bar_number_format": r"^\d{4,8}$",
    },
    "AZ": {
        "name": "State Bar of Arizona",
        "search": "https://azbar.legalserviceslink.com/",
        "bar_number_format": r"^\d{4,8}$",
    },
    "NV": {
        "name": "State Bar of Nevada",
        "search": "https://www.nvbar.org/find-a-lawyer/",
        "bar_number_format": r"^\d{4,8}$",
    },
    "NC": {
        "name": "North Carolina State Bar",
        "search": "https://www.ncbar.gov/lawyer-search/",
        "bar_number_format": r"^\d{4,8}$",
    },
}


# Practice area classification — keyword-based on business name
PRACTICE_AREAS: dict[str, list[str]] = {
    "personal_injury": [
        "injury", "accident", "tort", "negligence", "slip", "fall",
        "medical malpractice", "wrongful death", "car accident",
    ],
    "estate_planning": [
        "estate", "wills", "trust", "probate", "elder law",
        "power of attorney", "guardianship",
    ],
    "family_law": [
        "family law", "divorce", "custody", "child support",
        "adoption", "prenup",
    ],
    "criminal": [
        "criminal defense", "dui", "dwi", "felony", "misdemeanor",
        "defense attorney",
    ],
    "real_estate": [
        "real estate", "title", "zoning", "land use", "property",
    ],
    "business": [
        "business law", "corporate", "merger", "acquisition",
        "contract law", "intellectual property", "ip", "trademark",
        "startup", "llc", "incorporation",
    ],
    "immigration": [
        "immigration", "visa", "asylum", "naturalization", "deportation",
    ],
    "bankruptcy": [
        "bankruptcy", "chapter 7", "chapter 11", "chapter 13",
        "debt relief",
    ],
    "employment": [
        "employment", "labor", "discrimination", "wrongful termination",
        "harassment", "workplace",
    ],
    "tax": ["tax law", "tax attorney", "irs", "audit"],
}


@dataclass
class LawyerLead:
    """A lawyer / attorney lead."""
    name: str
    firm: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    practice_areas: list[str] = field(default_factory=list)
    bar_number: str = ""
    bar_state: str = ""
    source: str = "osm"
    latitude: float | None = None
    longitude: float | None = None


def _classify(name: str) -> list[str]:
    """Return practice areas for a firm/lawyer name."""
    if not name:
        return []
    name_lower = name.lower()
    matches: list[str] = []
    for area, keywords in PRACTICE_AREAS.items():
        if any(kw in name_lower for kw in keywords):
            matches.append(area)
    return matches


def _http_get(url: str, timeout: int = 8) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.info("[Legal] %s → %s", url, type(e).__name__)
        return None


def discover(
    niche: str = "legal",
    near: str = "New York, NY",
    state: str = "NY",
    practice_area: str = "",
    limit: int = 50,
) -> list[LawyerLead]:
    """Discover lawyers/attorneys.

    Args:
        niche: should be "legal".
        near: City hint for OSM.
        state: 2-letter state code for bar association lookup.
        practice_area: Filter by area (e.g. "personal_injury").
        limit: Max results.

    Returns:
        List of LawyerLead records.
    """
    from .overpass import discover as overpass_discover
    raw = overpass_discover(niche="legal", near=near, radius_m=25000, limit=limit)

    leads: list[LawyerLead] = []
    for c in raw:
        areas = _classify(c.name)
        if practice_area and practice_area not in areas:
            continue
        leads.append(LawyerLead(
            name=c.name,
            firm=c.name,
            phone=c.phone,
            address=c.address,
            city=c.city,
            state=c.state or state,
            zip=c.zip_code,
            practice_areas=areas,
            bar_state=c.state or state,
            source="osm:lawyer",
            latitude=c.latitude,
            longitude=c.longitude,
        ))

    log.info("[Legal] %d leads in %s (practice_area=%s)",
             len(leads), near, practice_area or "any")
    return leads


def list_states() -> list[str]:
    return list(STATE_BARS.keys())


def bar_url(state: str) -> Optional[str]:
    """Return public bar search URL for a state."""
    bar = STATE_BARS.get(state.upper())
    return bar.get("search") if bar else None
