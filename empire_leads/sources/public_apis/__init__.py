"""
public-apis source factory — auto-generate empire-leads sources
from the github.com/public-apis/public-apis catalog.

Usage from Python:
    from empire_leads.sources.public_apis import (
        get_catalog, filter_catalog, generate, discover,
    )

    catalog = get_catalog()                    # ~1400 entries, cached 24h
    free_no_auth = filter_catalog(catalog, auth="No", https_only=True)
    weather = filter_catalog(catalog, categories=["Weather"], auth="No")
    paths = generate(weather)                  # writes *.py files
    leads = discover("weather_apis", limit=10) # run all generated sources

CLI:
    python -m empire_leads.cli public-apis list                # all
    python -m empire_leads.cli public-apis list --category Weather --auth No
    python -m empire_leads.cli public-apis generate --category Weather --auth No
    python -m empire_leads.cli public-apis run weather_open_meteo --limit 5
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from .catalog import (
    ApiEntry,
    filter_catalog,
    get_catalog,
    list_categories,
)
from .generator import generate_source, generate_many

logger = logging.getLogger("empire-leads.public_apis")

GENERATED_DIR = Path(__file__).parent / "generated"


def generate(
    entries: list[ApiEntry] | None = None,
    *,
    categories: list[str] | None = None,
    auth: str | None = "No",
    https_only: bool = True,
    cors_yes_only: bool = False,
    keyword: str | None = None,
) -> list[Path]:
    """One-shot: filter catalog (or use passed entries) and write source files."""
    if entries is None:
        entries = get_catalog()
    entries = filter_catalog(
        entries,
        categories=categories,
        auth=auth,
        https_only=https_only,
        cors_yes_only=cors_yes_only,
        keyword=keyword,
    )
    return generate_many(entries)


def _load_generated(slug: str):
    """Import a generated source by slug. Returns the module or None."""
    try:
        return importlib.import_module(f".generated.{slug}", package=__name__)
    except ModuleNotFoundError:
        return None


def list_generated() -> list[Path]:
    """List already-generated source files on disk."""
    if not GENERATED_DIR.exists():
        return []
    return sorted(GENERATED_DIR.glob("*.py"))


def discover(source_slug: str, niche: str = "general", limit: int = 20, **kwargs):
    """Run a single generated source by slug. Returns list[Lead]."""
    mod = _load_generated(source_slug)
    if mod is None:
        raise FileNotFoundError(
            f"Source '{source_slug}' not generated. "
            f"Run: python -m empire_leads.cli public-apis generate --keyword <name>"
        )
    return mod.discover(niche=niche, limit=limit, **kwargs)


def discover_all_generated(niche: str = "general", limit_per_source: int = 20) -> dict:
    """Run every generated source and aggregate. Returns {slug: [Lead]}."""
    out: dict = {}
    for path in list_generated():
        slug = path.stem
        try:
            leads = discover(slug, niche=niche, limit=limit_per_source)
            out[slug] = leads
        except Exception as e:
            logger.warning("[%s] failed: %s", slug, e)
            out[slug] = []
    return out


__all__ = [
    "ApiEntry",
    "get_catalog",
    "filter_catalog",
    "list_categories",
    "generate",
    "generate_source",
    "generate_many",
    "discover",
    "discover_all_generated",
    "list_generated",
    "list_generated",
]