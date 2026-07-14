"""Engine — multi-source lead discovery orchestrator."""

from __future__ import annotations

import logging
import time
from typing import Optional

from .models import Lead, ScanResult
from .sources import overpass_discover
from .output import write_jsonl, write_csv, print_results

logger = logging.getLogger("empire-leads.engine")


def discover(
    niche: str,
    near: str = "",
    radius_m: int = 20000,
    limit: int = 50,
    sources: Optional[list[str]] = None,
) -> list[ScanResult]:
    """
    Discover leads across all configured sources.

    Args:
        niche: Business type (roofing, hvac, etc.)
        near: City/area or "lat,lon"
        radius_m: Search radius in meters
        limit: Max leads per source
        sources: Which sources to use (default: all available)
    """
    available = {"overpass": overpass_discover}
    active = {k: v for k, v in available.items() if not sources or k in sources}

    results: list[ScanResult] = []
    for name, fn in active.items():
        start = time.time()
        try:
            leads = fn(niche=niche, near=near, radius_m=radius_m, limit=limit)
            elapsed = time.time() - start
            results.append(ScanResult(
                source=name,
                niche=niche,
                leads=leads,
                elapsed_seconds=round(elapsed, 2),
            ))
            logger.info("%s/%s: %d leads in %.1fs", name, niche, len(leads), elapsed)
        except Exception as e:
            elapsed = time.time() - start
            logger.error("%s/%s failed after %.1fs: %s", name, niche, elapsed, e)
            results.append(ScanResult(
                source=name, niche=niche,
                elapsed_seconds=round(elapsed, 2),
                error=str(e),
            ))

    return results


def discover_batch(
    niches: list[str],
    near: str = "",
    radius_m: int = 20000,
    limit: int = 50,
    sources: Optional[list[str]] = None,
) -> list[ScanResult]:
    """Run discover for multiple niches."""
    all_results: list[ScanResult] = []
    for niche in niches:
        all_results.extend(discover(niche, near, radius_m, limit, sources))
    return all_results


def save_results(
    results: list[ScanResult],
    output_path: str = "",
    fmt: str = "jsonl",
    verbose: bool = False,
) -> int:
    """Save scan results and print summary. Returns total leads."""
    all_leads: list[Lead] = []
    for r in results:
        all_leads.extend(r.leads)

    if output_path:
        if fmt == "jsonl":
            count = write_jsonl(all_leads, output_path)
        elif fmt == "csv":
            count = write_csv(all_leads, output_path)
        else:
            raise ValueError(f"unsupported format: {fmt}")
        print(f"Wrote {count} leads to {output_path}")

    print_results(results, verbose=verbose)
    return len(all_leads)
