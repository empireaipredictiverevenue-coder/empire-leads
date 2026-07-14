"""Reddit no-API source — scrapes niche subreddits via old.reddit.com/.json

No API key required. Uses Mozilla/5.0 user-agent to fetch public JSON.
Ref: empire-revenue-pulsev2/scout.py (your existing codebase).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

from ..models import Lead

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Niche → list of subreddits to scan
NICHE_SUBREDDITS: dict[str, list[str]] = {
    "roofing": ["roofing", "Roofing", "RoofingSales", "construction"],
    "hvac": ["hvacadvice", "HVAC", "HVACadvice", "prohvac"],
    "plumbing": ["plumbing", "Plumbing", "plumbers", "PROPlumbing"],
    "contractor": ["contractor", "Contractor", "construction", "GeneralContractor"],
    "solar": ["solar", "SolarDIY", "Solarbusiness"],
    "landscaping": ["landscaping", "Landscaping", "lawncare"],
}

# Buying-intent keywords (from predictive-cloud/alpha_scout.py)
INTENT_KEYWORDS = [
    "need", "looking for", "hiring", "recommend", "recommendation",
    "help with", "suggestion", "anyone know", "advice", "quote",
    "estimate", "cost", "price", "problem with", "issue with",
    "broken", "repair", "replace", "installation",
]


def _has_intent(title: str, text: str = "") -> tuple[bool, int]:
    """Check if a post shows buying intent. Returns (match, hit_count)."""
    combined = (title + " " + text).lower()
    hits = sum(1 for kw in INTENT_KEYWORDS if kw in combined)
    return hits > 0, hits


def discover(
    niche: str,
    subreddit: Optional[str] = None,
    limit: int = 25,
    rate_delay: float = 2.0,
) -> list[Lead]:
    """Scrape Reddit for leads in niche-related subreddits.

    Args:
        niche: Target niche (e.g. "roofing", "hvac").
        subreddit: Specific subreddit. If None, scans all mapped to the niche.
        limit: Posts per subreddit.
        rate_delay: Seconds between API calls.
    """
    subreddits = [subreddit] if subreddit else NICHE_SUBREDDITS.get(niche, [])
    if not subreddits:
        log.warning(f"[Reddit] No subreddits mapped for niche '{niche}'")
        return []

    leads: list[Lead] = []
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit={limit}"
        log.info(f"[Reddit] Scanning r/{sub}...")

        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                log.warning(f"[Reddit] 403 Blocked — datacenter IP blocked by Reddit. Skipping.")
                break
            log.warning(f"[Reddit] r/{sub} fetch failed: HTTP {e.code}")
            time.sleep(rate_delay)
            continue
        except Exception as e:
            log.warning(f"[Reddit] r/{sub} fetch failed: {e}")
            time.sleep(rate_delay)
            continue

        posts = data.get("data", {}).get("children", [])
        for post in posts:
            item = post.get("data", {})
            title = item.get("title", "")
            text = item.get("selftext", "")
            subreddit_name = item.get("subreddit", sub)
            author = item.get("author", "[deleted]")
            permalink = item.get("permalink", "")
            score = item.get("score", 0)
            num_comments = item.get("num_comments", 0)
            post_id = item.get("id", "")

            # Skip stickied posts
            if item.get("stickied"):
                continue

            has_intent, hit_count = _has_intent(title, text)
            if not has_intent and hit_count == 0:
                continue

            # Truncate text for preview
            about = (text[:300] + "…") if len(text) > 300 else text
            url_full = f"https://reddit.com{permalink}"

            leads.append(Lead(
                name=title.strip(),
                source="reddit",
                niche=niche,
                subreddit=subreddit_name,
                about=about,
                social_links=url_full,
                rating=score,
                # phone/website/email won't be available from Reddit
                # but the buying-intent signal is the value
                raw={
                    "post_id": post_id,
                    "author": author,
                    "score": score,
                    "comments": num_comments,
                    "intent_hits": hit_count,
                },
            ))

        log.info(f"[Reddit] r/{sub}: {len([p for p in posts if not p['data'].get('stickied')])} posts → "
                 f"{len(leads)} buying-intent signals")

        time.sleep(rate_delay)

    log.info(f"[Reddit] Total: {len(leads)} leads from {len(subreddits)} subreddits")
    return leads
