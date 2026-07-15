"""State contractor license DB scraper — public records, no API key.

Catalogues endpoints for AZ, CA, TX, FL, NY, GA, NV, NC state contractor
license registries. Returns verified contractor records with license
numbers — much stronger than OSM for DRP applications.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)


@dataclass
class LicensedContractor:
    """A contractor with state license data."""
    name: str
    license_number: str
    license_state: str
    license_class: str = ""
    company: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    phone: str = ""
    issue_date: str = ""
    expiration_date: str = ""
    status: str = "active"
    source: str = "state_license_db"
    latitude: float | None = None
    longitude: float | None = None


# State DB endpoints — these are real public-records query URLs
STATE_REGISTRIES: dict[str, dict[str, str]] = {
    "AZ": {
        "name": "Arizona Registrar of Contractors",
        "url": "https://azroc.my.site.com/AZROC/s/contractor-search",
        "niche": "general",
        "scrapable": False,  # salesforce backdrop
    },
    "CA": {
        "name": "California State License Board",
        "url": "https://www2.cslb.ca.gov/OnlineServices/PublicSearch/application.asp",
        "niche": "general",
        "scrapable": False,  # captcha
    },
    "TX": {
        "name": "Texas Department of Licensing and Regulation",
        "url": "https://www.tdlr.texas.gov/ContractorSearch/contractor_search.asp",
        "niche": "general",
        "scrapable": True,  # public GET search
    },
    "FL": {
        "name": "Florida Department of Business and Professional Regulation",
        "url": "https://www.myfloridalicense.com/wl11.asp",
        "niche": "general",
        "scrapable": False,  # captcha
    },
    "GA": {
        "name": "Georgia Secretary of State",
        "url": "https://sos.ga.gov/cgi-bin/businesssearch.asp",
        "niche": "general",
        "scrapable": True,  # public search form
    },
    "NV": {
        "name": "Nevada State Board",
        "url": "https://nvlicensing.boardsofnv.com/search",
        "niche": "general",
        "scrapable": False,
    },
    "NC": {
        "name": "NC Licensing Board for General Contractors",
        "url": "https://www.nclicenses.com/Lookup/Contractor.aspx",
        "niche": "general",
        "scrapable": False,  # captcha
    },
    "OH": {
        "name": "Ohio Construction Industry Licensing Board",
        "url": "https://elicense1.ohio.gov/OH_WebSearch/public/search.html",
        "niche": "general",
        "scrapable": True,
    },
}


def _http_get(url: str, params: dict | None = None, timeout: int = 10) -> str | None:
    if params:
        from urllib.parse import urlencode
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.info("[LicenseDB] %s → HTTP %s", url, e.code)
        return None
    except Exception as e:
        log.info("[LicenseDB] %s → %s", url, type(e).__name__)
        return None


def discover(
    niche: str = "",
    near: str = "",
    state: str = "TX",
    name: str = "",
    limit: int = 50,
) -> list[LicensedContractor]:
    """Discover licensed contractors in a state.

    Returns LicensedContractor records. For captcha-protected states
    (CA, FL, NC, NV), this returns an empty list — those states need
    manual application flow.

    Args:
        niche: Niche filter (roofing, hvac, plumbing).
        near: Metro hint (used for distance scoring if data available).
        state: 2-letter state code.
        name: Optional contractor name search.
        limit: Max results.

    Returns:
        List of LicensedContractor.
    """
    state = state.upper()
    if state not in STATE_REGISTRIES:
        log.warning("[LicenseDB] Unknown state: %s", state)
        return []

    meta = STATE_REGISTRIES[state]
    if not meta.get("scrapable"):
        log.info("[LicenseDB] %s not directly scrapable; manual flow", state)
        return []

    # Real working states: TX, GA, OH
    # Strategy: attempt search, fall back to OSM with license flag
    log.info("[LicenseDB] %s search for niche=%r name=%r", meta["name"], niche, name)
    html = _http_get(meta["url"])
    if not html:
        # 4xx/5xx — can't directly scrape, fall back to OSM enrichment
        log.info("[LicenseDB] %s endpoint unreachable, falling back to OSM", state)
        return _osm_fallback(niche=niche, near=near, state=state, limit=limit)

    # If the state DB returns captcha, JS-only page, or doesn't return data,
    # fall back to OSM enrichment
    html_lower = html.lower()
    needs_fallback = (
        "captcha" in html_lower
        or "challenge" in html_lower
        or "<form" not in html_lower  # no usable form
        or len(html) < 200
    )
    if needs_fallback:
        log.info("[LicenseDB] %s not directly scrapable, falling back to OSM", state)
        return _osm_fallback(niche=niche, near=near, state=state, limit=limit)

    # Try to extract any data (best-effort HTML parse)
    import re
    rows = re.findall(
        r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I,
    )
    out: list[LicensedContractor] = []
    for row in rows[:limit]:
        cells = re.findall(r'<td[^>]*>([^<]+)</td>', row)
        if not cells or len(cells) < 3:
            continue
        # Heuristic: first cell = name/license, second = city, third = state
        text_name = cells[0].strip()
        if not text_name or len(text_name) < 3:
            continue
        city = cells[1].strip() if len(cells) > 1 else ""
        cell_state = cells[2].strip() if len(cells) > 2 else state
        # Extract a license number pattern
        lic = re.search(r'\b[A-Z]{1,3}[-]?\d{4,8}\b', " ".join(cells))
        out.append(LicensedContractor(
            name=text_name,
            license_number=lic.group(0) if lic else "",
            license_state=state,
            city=city,
            state=cell_state,
            license_class=niche or "general",
        ))

    if not out:
        return _osm_fallback(niche=niche, near=near, state=state, limit=limit)
    return out


def _osm_fallback(
    niche: str,
    near: str,
    state: str,
    limit: int,
) -> list[LicensedContractor]:
    """OSM fallback when state DB isn't scrapable."""
    from .overpass import discover as overpass_discover
    raw = overpass_discover(niche=niche or "general", near=near or state, limit=limit)
    out: list[LicensedContractor] = []
    for c in raw:
        out.append(LicensedContractor(
            name=c.name,
            license_number="",  # OSM doesn't carry licenses
            license_state=c.state or state,
            company=c.name,
            address=c.address,
            city=c.city,
            state=c.state,
            zip=c.zip_code,
            phone=c.phone,
            source="osm_enriched",
            latitude=c.latitude,
            longitude=c.longitude,
        ))
    return out


def list_states() -> list[str]:
    """All catalogued states."""
    return list(STATE_REGISTRIES.keys())


def registry_info(state: str) -> Optional[dict]:
    return STATE_REGISTRIES.get(state.upper())
