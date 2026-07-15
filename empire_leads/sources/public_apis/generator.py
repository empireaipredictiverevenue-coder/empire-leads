"""
Generate empire-leads source files from a public-apis catalog entry.

Each generated source:
    - lives under empire_leads/sources/public_apis/generated/<slug>.py
    - exports a `discover(niche, limit=20, **kwargs)` function
    - returns list[Lead]
    - has a TODO header noting auth requirements and v1 stub behavior

For "No" auth APIs the generator creates a working GET stub that
hits the docs URL and attempts to parse JSON; if the docs URL
returns HTML it returns [] gracefully. v2 hand-edits replace the
stub with the real endpoint.
"""
from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

from .catalog import ApiEntry

logger = logging.getLogger("empire-leads.public_apis.generator")

GENERATED_DIR = Path(__file__).parent / "generated"

GENERATED_HEADER = '''\
"""Auto-generated source from public-apis catalog.

API:        {name}
Description:{description}
Category:   {category}
Auth:       {auth}
HTTPS:      {https}
CORS:       {cors}
Docs:       {docs_url}

This is a v1 STUB. It hits the docs URL and tries to parse JSON.
Many public-api "docs" pages return HTML, in which case this
source returns []. To make it real:
  1. Read the docs at: {docs_url}
  2. Replace the `_fetch()` body with the real endpoint + params
  3. Map the response fields into Lead() in `_to_lead()`
"""
'''

GENERATED_BODY = '''\

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ....models import Lead

logger = logging.getLogger("empire-leads.public_apis.{slug}")

API_URL = "{url}"
TIMEOUT = 15
USER_AGENT = "EmpireLeads/0.1 (public-apis source; founder@empire-ai.co.uk)"


def _fetch(limit: int = 20) -> list[dict]:
    """GET the docs URL (v1 stub). Returns parsed JSON list, or []."""
    try:
        req = urllib.request.Request(
            API_URL, headers={{"User-Agent": USER_AGENT, "Accept": "application/json"}}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.info("[{slug}] docs URL returned non-JSON (HTML?) — stub returns []")
            return []
        if isinstance(data, list):
            return data[:limit]
        if isinstance(data, dict):
            # common: {{"results": [...]}} or {{"data": [...]}} or {{"items": [...]}}
            for k in ("results", "data", "items", "records", "entries"):
                if k in data and isinstance(data[k], list):
                    return data[k][:limit]
            return [data]  # single object
        return []
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("[{slug}] fetch failed: %s", e)
        return []


def _to_lead(item: dict, niche: str) -> Lead:
    """Map a single API response item to a Lead. v1 best-effort."""
    name = (
        item.get("name")
        or item.get("title")
        or item.get("company")
        or item.get("business_name")
        or "{name}"
    )
    return Lead(
        name=str(name)[:200],
        source="public_apis:{slug}",
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
        category=str(item.get("category") or "{category}"),
        about=str(item.get("description") or "")[:500],
        raw=item,
    )


def discover(niche: str = "general", limit: int = 20, **kwargs) -> list[Lead]:
    """v1 stub: hit docs URL, parse JSON if possible."""
    items = _fetch(limit=limit)
    return [_to_lead(it, niche) for it in items]
'''


def generate_source(entry: ApiEntry) -> Path:
    """Write a source file for the given entry. Returns the path.

    Overwrites if it exists. Skips if slug collides with existing file
    unless overwrite=True.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    target = GENERATED_DIR / f"{entry.slug}.py"

    header = GENERATED_HEADER.format(
        name=entry.name,
        description=entry.description,
        category=entry.category,
        auth=entry.auth,
        https=entry.https,
        cors=entry.cors,
        docs_url=entry.docs_url or entry.url,
    )
    body = GENERATED_BODY.format(
        slug=entry.slug,
        name=entry.name,
        category=entry.category,
        url=entry.url or entry.docs_url or "",
    )
    target.write_text(header + body)
    logger.info("Generated %s", target)
    return target


def generate_many(entries: list[ApiEntry]) -> list[Path]:
    return [generate_source(e) for e in entries]