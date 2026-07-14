"""Lead data model — unified schema for all sources."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Lead:
    """A single discovered prospect, regardless of source."""

    # ── Core ────────────────────────────────────────────────
    name: str
    source: str           # e.g. "overpass", "reddit", "nws", "google_places"
    niche: str            # e.g. "roofing", "hvac"

    # ── Contact ─────────────────────────────────────────────
    phone: str = ""
    website: str = ""
    email: str = ""

    # ── Location ────────────────────────────────────────────
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    latitude: float | None = None
    longitude: float | None = None

    # ── Enrichment ──────────────────────────────────────────
    rating: float | None = None
    category: str = ""
    hours: str = ""
    about: str = ""
    social_links: str = ""
    subreddit: str = ""

    # ── Metadata ────────────────────────────────────────────
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw: dict | None = None  # original source payload

    def to_dict(self) -> dict:
        return asdict(self)

    def to_jsonl(self) -> str:
        import json
        return json.dumps(self.to_dict(), default=str)


@dataclass
class ScanResult:
    """Aggregated result from multi-source discovery."""
    source: str
    niche: str
    leads: list[Lead] = field(default_factory=list)
    total_found: int = 0
    total_deduped: int = 0
    time_s: float = 0.0
    results: dict | None = None  # per-source breakdown
