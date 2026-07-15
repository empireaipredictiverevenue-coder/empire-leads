"""
public-apis/README.md parser → structured catalog.

Parses the community-curated list of free public APIs from
github.com/public-apis/public-apis into a queryable in-memory
catalog. Cached to ~/.cache/empire-leads/public_apis.json.

Output schema per API:
    {
        "name":       "Cat Facts",
        "slug":       "cat_facts",
        "description":"Random cat facts",
        "url":        "https://catfact.ninja/",
        "docs_url":   "https://catfact.ninja/",
        "auth":       "No",                  # No | apiKey | OAuth | X-Mashape-Key
        "https":      true,
        "cors":       "Yes",                 # Yes | No | Unknown
        "category":   "Animals",
        "fetch_url":  None,                  # populated by generator if discoverable
    }

The README tables are flat (no per-row fetch URL) so the catalog
stops at "link to docs". The generator (generator.py) then emits
a source skeleton per API that, in v1, hits the docs URL with
?format=json or a common guess. v2 (manual) replaces with a real
endpoint once you discover it.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("empire-leads.public_apis.catalog")

README_URL = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
CACHE_PATH = Path.home() / ".cache" / "empire-leads" / "public_apis.json"
CACHE_TTL_S = 24 * 3600  # 24h — README changes daily


@dataclass
class ApiEntry:
    name: str
    slug: str
    description: str
    url: str
    docs_url: str
    auth: str               # "No" | "apiKey" | "OAuth" | "X-Mashape-Key" | other
    https: bool
    cors: str               # "Yes" | "No" | "Unknown"
    category: str
    fetch_url: Optional[str] = None


def _slugify(name: str) -> str:
    """filesystem-safe slug: cat-facts → cat_facts."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "unnamed"


def _parse_readme(content: str) -> list[ApiEntry]:
    """Walk the README, section by section, parse each table.

    Sections start with `### CategoryName`. The first row after the
    header is `API | Description | Auth | HTTPS | CORS`. Subsequent
    rows have 5-6 columns.
    """
    entries: list[ApiEntry] = []
    lines = content.splitlines()
    current_category: Optional[str] = None
    in_header = False  # True after seeing the column-header row

    # Regex to extract: [name](url) from markdown link cells
    link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for raw in lines:
        line = raw.rstrip()

        # Section header
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            current_category = m.group(1).strip()
            in_header = False
            continue

        # Column header row — tolerate missing leading pipe in some sections
        if current_category and re.match(
            r"^\|?\s*API\s*\|\s*Description\s*\|\s*Auth\s*\|", line
        ):
            in_header = True
            continue

        # Separator row (|:---|:---|...) — also tolerate missing leading pipe
        if in_header and re.match(r"^\|?[\s\-:|]+\|?\s*$", line) and "---" in line:
            continue

        # Data row
        if in_header and line.startswith("|") and current_category:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5:
                continue  # malformed

            name_cell, desc_cell, auth_cell, https_cell, cors_cell = cells[:5]

            # First cell: [name](url) (with possible utm params)
            m1 = link_re.search(name_cell)
            if not m1:
                # Some entries have plain text in name
                name = name_cell.strip() or "(unnamed)"
                url = ""
            else:
                name = m1.group(1).strip()
                url = m1.group(2).strip()

            # Last cell: link to docs (Postman button or docs link)
            docs_url = ""
            if len(cells) >= 6:
                m2 = link_re.search(cells[5])
                if m2:
                    docs_url = m2.group(2).strip()
            if not docs_url:
                docs_url = url

            entries.append(
                ApiEntry(
                    name=name,
                    slug=_slugify(name),
                    description=desc_cell.strip(),
                    url=url,
                    docs_url=docs_url,
                    auth=auth_cell.strip().strip("`"),
                    https=https_cell.strip().lower() == "yes",
                    cors=cors_cell.strip(),
                    category=current_category,
                )
            )

    return entries


def _download_readme() -> str:
    """Fetch the public-apis README. 30s timeout."""
    req = urllib.request.Request(
        README_URL, headers={"User-Agent": "EmpireLeads/0.1 (public-apis sync)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def get_catalog(force_refresh: bool = False) -> list[ApiEntry]:
    """Return the parsed catalog, using disk cache if fresh.

    Raises:
        urllib.error.URLError: if download fails and no cache exists.
    """
    if not force_refresh and CACHE_PATH.exists():
        age = time.time() - CACHE_PATH.stat().st_mtime
        if age < CACHE_TTL_S:
            try:
                data = json.loads(CACHE_PATH.read_text())
                return [ApiEntry(**d) for d in data]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Cache corrupt, refreshing: %s", e)

    content = _download_readme()
    entries = _parse_readme(content)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([asdict(e) for e in entries], indent=2))
    logger.info("Cached %d APIs to %s", len(entries), CACHE_PATH)
    return entries


def filter_catalog(
    entries: list[ApiEntry],
    *,
    categories: Optional[list[str]] = None,
    auth: Optional[str] = None,           # exact match, e.g. "No"
    https_only: bool = True,
    cors_yes_only: bool = False,
    keyword: Optional[str] = None,        # search name + description
) -> list[ApiEntry]:
    """Apply common filters. Returns list (may be empty)."""
    out: list[ApiEntry] = []
    kw = keyword.lower() if keyword else None
    for e in entries:
        if categories and e.category not in categories:
            continue
        if auth and e.auth != auth:
            continue
        if https_only and not e.https:
            continue
        if cors_yes_only and e.cors != "Yes":
            continue
        if kw and kw not in e.name.lower() and kw not in e.description.lower():
            continue
        out.append(e)
    return out


def list_categories(entries: list[ApiEntry]) -> dict[str, int]:
    """Return {category_name: count}, sorted by name."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1
    return dict(sorted(counts.items()))