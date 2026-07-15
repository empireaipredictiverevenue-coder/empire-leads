"""trend-scanner: 'research lab' from the space-station blueprint.

Scans public sources for what's already selling, ranks by signal,
outputs hot niches per metro. No paid APIs. Free-tier friendly.

Sources:
  - reddit    : top posts per niche-subreddit (engagement = demand)
  - overpass  : business density per niche per metro (supply)
  - craigslist: listing count per niche per city (supply+velocity)
  - nws       : active severe weather (storm = repair demand spike)
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Trend:
    niche: str
    metro: str
    score: float
    signals: dict = field(default_factory=dict)
    source: str = "trend-scanner"
    captured_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# ── reddit: top posts per niche subreddit ──────────────────────────
def _reddit_score(niche: str, limit: int = 25) -> tuple[float, dict]:
    """Higher score = more engagement = more demand signal."""
    sub_map = {
        "roofing": "Roofing",
        "hvac": "HVAC",
        "plumbing": "plumbing",
        "electrical": "electricians",
        "landscaping": "landscaping",
        "pest_control": "pestcontrol",
        "cleaning": "CleaningTips",
        "moving": "moving",
        "auto_repair": "autoshop",
        "personal_injury": "personalfinance",
        "estate_planning": "EstatePlanning",
        "solar": "solar",
    }
    sub = sub_map.get(niche, niche.replace("_", ""))
    url = f"https://old.reddit.com/r/{sub}/top.json?t=month&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 trend-scanner"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        log.warning("reddit fail %s: %s", niche, e)
        return 0.0, {"error": str(e)}

    children = data.get("data", {}).get("children", [])
    if not children:
        return 0.0, {"posts": 0}
    total_score = sum(c["data"].get("score", 0) for c in children)
    total_comments = sum(c["data"].get("num_comments", 0) for c in children)
    # normalize: avg score per post, log scale
    avg = total_score / max(len(children), 1)
    norm = min(avg / 50.0, 1.0)  # cap at 1.0
    return norm, {"posts": len(children), "avg_score": avg, "comments": total_comments}


# ── overpass: business density per niche per metro ─────────────────
def _overpass_score(niche: str, near: str, radius_m: int = 20000) -> tuple[float, dict]:
    """More competitors = proven market. Less = white space."""
    from .sources.overpass import BUSINESS_TAGS
    # find tags for this niche
    tags = [t for n, k, v in BUSINESS_TAGS if n == niche]
    if not tags:
        return 0.0, {"error": f"no overpass tags for {niche}"}

    # geocode via nominatim
    geo_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(near)}&format=json&limit=1"
    try:
        with urllib.request.urlopen(geo_url, timeout=10) as r:
            geo = json.loads(r.read().decode("utf-8", errors="replace"))
        if not geo:
            return 0.0, {"error": "geocode fail"}
        lat, lon = float(geo[0]["lat"]), float(geo[0]["lon"])
    except Exception as e:
        return 0.0, {"error": str(e)}

    # overpass query
    tag_filters = "".join(f'["{k}"="{v}"]' for k, v in tags)
    q = (
        "[out:json][timeout:15];"
        f"(node{tag_filters}(around:{radius_m},{lat},{lon});"
        f"way{tag_filters}(around:{radius_m},{lat},{lon}););"
        "out count;"
    )
    op_url = f"https://overpass-api.de/api/interpreter?data={urllib.parse.quote(q)}"
    try:
        with urllib.request.urlopen(op_url, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        count = data.get("elements", [{}])[0].get("tags", {}).get("ways", 0)
        count += data.get("elements", [{}])[0].get("tags", {}).get("nodes", 0)
        # also sum nodes/ways from second element if present
        for el in data.get("elements", [])[1:]:
            count += int(el.get("tags", {}).get("ways", 0)) + int(el.get("tags", {}).get("nodes", 0))
    except Exception as e:
        return 0.0, {"error": str(e)}

    # density buckets: <5 = sparse, 5-20 = ok, 20-50 = saturated, >50 = hyper
    if count < 5:
        density = 0.3  # white space
    elif count < 20:
        density = 0.7  # proven
    elif count < 50:
        density = 0.9  # hot market
    else:
        density = 0.5  # saturated, harder entry
    return density, {"count": count, "lat": lat, "lon": lon}


# ── craigslist: listing velocity per niche per city ─────────────────
_CRAIGSLIST_CITIES = {
    "Phoenix, AZ": "phoenix",
    "Los Angeles, CA": "losangeles",
    "San Diego, CA": "sandiego",
    "San Francisco, CA": "sfbay",
    "Denver, CO": "denver",
    "Dallas, TX": "dallas",
    "Houston, TX": "houston",
    "Austin, TX": "austin",
    "Miami, FL": "miami",
    "Atlanta, GA": "atlanta",
    "Chicago, IL": "chicago",
    "New York, NY": "newyork",
    "Seattle, WA": "seattle",
    "Boston, MA": "boston",
    "Philadelphia, PA": "philadelphia",
}

_CRAIGSLIST_SEARCH = {
    "roofing": "roofer",
    "hvac": "hvac",
    "plumbing": "plumber",
    "electrical": "electrician",
    "landscaping": "landscaping",
    "cleaning": "house cleaning",
    "moving": "movers",
    "auto_repair": "auto repair",
    "solar": "solar",
    "pest_control": "exterminator",
}


def _craigslist_score(niche: str, near: str) -> tuple[float, dict]:
    """Listing count under 'services' per city."""
    city_key = _CRAIGSLIST_CITIES.get(near)
    if not city_key:
        return 0.0, {"error": "city not in craigslist map"}
    query = _CRAIGSLIST_SEARCH.get(niche, niche)
    url = f"https://{city_key}.craigslist.org/search/sss?query={urllib.parse.quote(query)}&sort=date"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 trend-scanner"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0.0, {"error": str(e)}

    # crude count: count result rows
    matches = len(re.findall(r'class="result-row"', html))
    # also count "service" hits in titles
    if matches == 0:
        matches = len(re.findall(r'<a[^>]+href="[^"]+craigslist[^"]+"[^>]*>', html))

    # bucket
    if matches < 20:
        score = 0.4
    elif matches < 80:
        score = 0.7
    elif matches < 200:
        score = 0.9
    else:
        score = 0.6  # saturated
    return score, {"listings": matches, "city": city_key}


# ── combined trend score ───────────────────────────────────────────
def score_trend(
    niche: str,
    metros: list[str],
    sources: Optional[list[str]] = None,
) -> list[Trend]:
    """Score a niche across multiple metros. Returns sorted by score desc."""
    if sources is None:
        sources = ["reddit", "overpass", "craigslist"]

    results = []
    for metro in metros:
        signals = {}
        scores = []

        if "reddit" in sources:
            s, sig = _reddit_score(niche)
            signals["reddit"] = sig
            scores.append(s)

        if "overpass" in sources:
            s, sig = _overpass_score(niche, metro)
            signals["overpass"] = sig
            scores.append(s)

        if "craigslist" in sources:
            s, sig = _craigslist_score(niche, metro)
            signals["craigslist"] = sig
            scores.append(s)

        # weighted average: reddit 0.4, overpass 0.35, craigslist 0.25
        weights = {"reddit": 0.4, "overpass": 0.35, "craigslist": 0.25}
        used = [w for src, w in weights.items() if src in sources]
        total_weight = sum(used) or 1
        weighted = sum(s * w for s, w in zip(scores, used)) / total_weight

        results.append(Trend(niche=niche, metro=metro, score=round(weighted, 3), signals=signals))

    results.sort(key=lambda t: t.score, reverse=True)
    return results
