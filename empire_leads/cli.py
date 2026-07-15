#!/usr/bin/env python3
"""CLI entry point — `empire-leads discover`, `batch`, `list-sources`, `list-niches`."""

from __future__ import annotations

import argparse
import logging
import sys

from .engine import discover, list_sources
from .models import Lead, ScanResult
from .output import save_results

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="empire-leads",
        description="Zero-Chrome B2B lead discovery engine. Free, no API keys.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ── discover ──────────────────────────────────────────
    disc = sub.add_parser("discover", help="Discover leads for one niche")
    disc.add_argument("niche", help="Business type (roofing, hvac, plumbing, etc.)")
    disc.add_argument("--near", default="Phoenix, AZ", help="City/area or 'lat,lon'")
    disc.add_argument("--lat", type=float, help="Latitude override")
    disc.add_argument("--lon", type=float, help="Longitude override")
    disc.add_argument("--state", help="State filter (for NWS storm alerts)")
    disc.add_argument("--radius", type=int, default=20000, help="Search radius in meters")
    disc.add_argument("--limit", type=int, default=20, help="Max leads per source")
    disc.add_argument("--sources", nargs="*", help="Sources to use (default: all)")
    disc.add_argument("--output", "-o", default="", help="Output file path")
    disc.add_argument("--format", "-f", choices=["jsonl", "csv"], default="jsonl", help="Output format")
    disc.add_argument("--verbose", "-v", action="store_true", help="Show lead details")
    disc.add_argument("--quiet", "-q", action="store_true", help="Suppress info logging")

    # ── batch ─────────────────────────────────────────────
    batch = sub.add_parser("batch", help="Run discover for multiple niches")
    batch.add_argument("--niches", nargs="*", help="Niches to scan (inline)")
    batch.add_argument("--file", help="File with one niche per line")
    batch.add_argument("--near", default="Phoenix, AZ", help="City/area or 'lat,lon'")
    batch.add_argument("--radius", type=int, default=20000, help="Search radius")
    batch.add_argument("--limit", type=int, default=20, help="Max leads per source")
    batch.add_argument("--output", "-o", default="", help="Output file path")
    batch.add_argument("--format", "-f", choices=["jsonl", "csv"], default="jsonl")
    batch.add_argument("--verbose", "-v", action="store_true", help="Show lead details")
    batch.add_argument("--quiet", "-q", action="store_true", help="Suppress info logging")

    # ── list-sources ──────────────────────────────────────
    sub.add_parser("list-sources", help="List available lead sources")

    # ── list-niches ───────────────────────────────────────
    sub.add_parser("list-niches", help="List supported business niches")

    return p


def _cmd_discover(args: argparse.Namespace) -> int:
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    result = discover(
        niche=args.niche,
        near=args.near,
        sources=args.sources,
        lat=args.lat,
        lon=args.lon,
        state=args.state,
        limit_per_source=args.limit,
    )
    return save_results(result, args.output, args.format, args.verbose)


def _cmd_batch(args: argparse.Namespace) -> int:
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    niches: list[str] = []
    if args.niches:
        niches.extend(args.niches)
    if args.file:
        with open(args.file) as f:
            niches.extend(line.strip() for line in f if line.strip())

    if not niches:
        print("error: specify --niches or --file", file=sys.stderr)
        return 1

    all_leads: list[Lead] = []
    combined_results: dict[str, dict] = {}
    for niche in niches:
        r = discover(
            niche=niche,
            near=args.near,
            limit_per_source=args.limit,
        )
        all_leads.extend(r.leads)
        combined_results[niche] = r.results

    result = ScanResult(
        source="batch",
        niche=",".join(niches),
        leads=all_leads,
        total_found=len(all_leads),
        total_deduped=len(all_leads),
        time_s=0,
        results=combined_results,
    )
    return save_results(result, args.output, args.format, args.verbose)


def _cmd_list_sources() -> int:
    sources = list_sources()
    from .sources import SOURCE_DESCRIPTIONS
    print("Available lead sources:")
    for name in sources:
        desc = SOURCE_DESCRIPTIONS.get(name, "")
        print(f"  {name:20s} {desc}")
    return 0

def _cmd_list_niches() -> int:
    from .sources.overpass import BUSINESS_TAGS
    seen = set()
    print("Supported business niches:")
    for n, key, val in BUSINESS_TAGS:
        if n not in seen:
            seen.add(n)
            print(f"  {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "discover":
        return _cmd_discover(args)
    elif args.command == "batch":
        return _cmd_batch(args)
    elif args.command == "list-sources":
        return _cmd_list_sources()
    elif args.command == "list-niches":
        return _cmd_list_niches()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
