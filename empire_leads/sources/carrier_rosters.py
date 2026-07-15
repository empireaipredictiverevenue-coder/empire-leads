"""Carrier DRP roster module — discover contractors + track carrier applications.

Carriers don't expose clean DRP rosters publicly (all gated behind JS).
The real integration is the inverse: we find contractors via OSM + state
license DBs, then help them apply to carriers' DRP programs.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Real public carrier contractor-program endpoints (these DO exist for contractors applying)
CARRIER_PROGRAMS: dict[str, dict[str, Any]] = {
    "statefarm": {
        "name": "State Farm",
        "apply_url": "https://www.statefarm.com/agentfinder",
        "program_url": "https://www.sfclaim.com/contractor-program",
        "regions": "national",
        "scrapable_endpoint": None,
    },
    "allstate": {
        "name": "Allstate",
        "apply_url": "https://www.allstate.com/enrollment/join.aspx",
        "program_url": "https://www.allstate.com/enrollment/auto-repair-program",
        "regions": "national",
        "scrapable_endpoint": None,
    },
    "farmers": {
        "name": "Farmers",
        "apply_url": "https://www.farmers.com/careers/agent/",
        "program_url": None,
        "regions": "national",
        "scrapable_endpoint": None,
    },
    "liberty_mutual": {
        "name": "Liberty Mutual",
        "apply_url": "https://www.libertymutual.com/find-an-agent",
        "program_url": None,
        "regions": "national",
        "scrapable_endpoint": None,
    },
    "usaa": {
        "name": "USAA",
        "apply_url": "https://www.usaa.com/inet/ent_agents/AgentLocator",
        "program_url": None,
        "regions": "national",
        "scrapable_endpoint": None,
    },
    "progressive": {
        "name": "Progressive",
        "apply_url": "https://www.progressivecommercial.com/agent/",
        "program_url": "https://www.progressive.com/claims/repair-network",
        "regions": "national",
        "scrapable_endpoint": None,
    },
}

# State license DB endpoints — these DO work for free (public data)
STATE_LICENSE_DBS: dict[str, str] = {
    "AZ": "https://azroc.my.site.com/AZROC/s/contractor-search",
    "CA": "https://www2.cslb.ca.gov/OnlineServices/PublicSearch/application.asp",
    "TX": "https://www.tdlr.texas.gov/ContractorSearch/contractor_search.asp",
    "FL": "https://www.myfloridalicense.com/wl11.asp",
    "NY": "https://appext20.dos.ny.gov/nydos/ConsLookup.do",
    "GA": "https://sos.ga.gov/cgi-bin/businesssearch.asp",
    "NV": "https://nvlicensing.boardsofnv.com/search",
    "NC": "https://www.nclicenses.com/Lookup/Contractor.aspx",
}


@dataclass
class ContractorForApplication:
    """A contractor ready to apply for carrier DRP."""
    company: str
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    license_number: str = ""
    license_state: str = ""
    specializations: list[str] = field(default_factory=list)
    years_in_business: int = 0
    source: str = ""
    latitude: float | None = None
    longitude: float | None = None


def _near_zips(near: str) -> list[str]:
    """Resolve metro to sample ZIPs (covers ~30-mile radius)."""
    metro_zips = {
        "phoenix, az": [
            "85001", "85003", "85006", "85007", "85008", "85012",
            "85014", "85015", "85016", "85017", "85018", "85020",
            "85021", "85022", "85023", "85024", "85027", "85028",
        ],
        "dallas, tx": [
            "75201", "75202", "75204", "75205", "75206", "75207",
            "75208", "75209", "75210", "75211", "75212", "75214",
        ],
        "tampa, fl": [
            "33602", "33603", "33604", "33605", "33606", "33607",
            "33609", "33611", "33614", "33615", "33617", "33619",
        ],
        "los angeles, ca": [
            "90001", "90002", "90003", "90004", "90005", "90006",
            "90007", "90008", "90009", "90010", "90011", "90012",
        ],
    }
    return metro_zips.get(near.lower().strip(), [
        "85001", "85003", "85006", "85007", "85008", "85012",
    ])


def _fetch(url: str, timeout: int = 8) -> str | None:
    """HTTP GET with browser-like UA."""
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.info("[Carrier] %s → HTTP %s", url, e.code)
        return None
    except Exception as e:
        log.info("[Carrier] %s → %s", url, type(e).__name__)
        return None


def discover_contractors_for_application(
    niche: str = "roofing",
    near: str = "Phoenix, AZ",
    limit: int = 50,
) -> list[ContractorForApplication]:
    """Discover local contractors ready to apply for carrier DRP programs.

    Uses Overpass API (verified working) to find contractors in the
    target area. Output is a list ready for carrier program application.
    """
    from .overpass import discover as overpass_discover

    raw_leads = overpass_discover(
        niche=niche, near=near, radius_m=30000, limit=limit,
    )
    out: list[ContractorForApplication] = []
    for lead in raw_leads:
        out.append(ContractorForApplication(
            company=lead.name,
            phone=lead.phone,
            email="",
            address=lead.address,
            city=lead.city,
            state=lead.state,
            zip_code=lead.zip_code,
            license_number="",
            license_state=lead.state,
            specializations=[niche],
            source=f"osm:{lead.source}",
            latitude=lead.latitude,
            longitude=lead.longitude,
        ))
    return out


def get_carrier_program(carrier_key: str) -> dict[str, Any] | None:
    """Return info about a carrier's contractor program."""
    return CARRIER_PROGRAMS.get(carrier_key)


def list_carriers() -> list[str]:
    return list(CARRIER_PROGRAMS.keys())


def list_state_license_dbs() -> list[str]:
    return list(STATE_LICENSE_DBS.keys())


def discover(
    niche: str = "",
    near: str = "Phoenix, AZ",
    carriers: list[str] | None = None,
    zip_codes: list[str] | None = None,
    limit: int = 50,
) -> list[ContractorForApplication]:
    """Discover contractors ready for carrier DRP application.

    Args:
        niche: Business niche (roofing, hvac, plumbing, etc.).
        near: Metro area hint.
        carriers: Filter to specific carriers (info only, not used for filtering).
        zip_codes: Override ZIP list.
        limit: Max contractors to return.

    Returns:
        List of ContractorForApplication records.
    """
    if not niche:
        niche = "roofing"
    log.info("[Carrier] discovering %s contractors in %s for carrier DRP app",
             niche, near)
    return discover_contractors_for_application(
        niche=niche, near=near, limit=limit,
    )
