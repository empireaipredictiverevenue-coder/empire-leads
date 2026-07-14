#!/usr/bin/env python3
"""CLI entry point — `empire-leads discover` and `empire-leads batch`."""

from __future__ import annotations

import argparse
import logging
import sys

from .engine import discover, discover_batch, save_results
from .sources import overpass_discover

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
    disc = sub.add_parser("discover", help="Discover leads for one niche near a location")
    disc.add_argument("niche", help="Business type (roofing, hvac, plumbing, etc.)")
    disc.add_argument("--near", default="Phoenix, AZ", help="City/area or 'lat,lon'")
    disc.add_argument("--radius", type=int, default=20000, help="Search radius in meters")
    disc.add_argument("--limit", type=int, default=50, help="Max leads per source")
    disc.add_argument("--sources", nargs="*", help="Sources to use (default: all)")
    disc.add_argument("--output", "-o", default="", help="Output file path")
    disc.add_argument("--format", "-f", choices=["jsonl", "csv"], default="jsonl", help="Output format")
    disc.add_argument("--verbose", "-v", action="store_true", help="Show lead details")
    disc.add_argument("--quiet", "-q", action="store_true", help="Suppress info logging")

    # ── batch ─────────────────────────────────────────────
    batch = sub.add_parser("batch", help="Run discover for multiple niches from file")
    batch.add_argument("--niches", nargs="*", help="Niches to scan (inline)")
    batch.add_argument("--file", help="File with one niche per line")
    batch.add_argument("--near", default="Phoenix, AZ", help="City/area or 'lat,lon'")
    batch.add_argument("--radius", type=int, default=20000, help="Search radius in meters")
    batch.add_argument("--limit", type=int, default=50, help="Max leads per source")
    batch.add_argument("--output", "-o", default="", help="Output file path")
    batch.add_argument("--format", "-f", choices=["jsonl", "csv"], default="jsonl")
    batch.add_argument("--verbose", "-v", action="store_true", help="Show lead details")

    # ── list-sources ──────────────────────────────────────
    sub.add_parser("list-sources", help="List available lead sources")

    # ── list-niches ───────────────────────────────────────
    niche_help = sub.add_parser("list-niches", help="List supported business niches")

    return p


def _cmd_discover(args: argparse.Namespace) -> int:
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    results = discover(
        niche=args.niche,
        near=args.near,
        radius_m=args.radius,
        limit=args.limit,
        sources=args.sources,
    )
    return save_results(results, args.output, args.format, args.verbose)


def _cmd_batch(args: argparse.Namespace) -> int:
    niches: list[str] = []
    if args.niches:
        niches.extend(args.niches)
    if args.file:
        with open(args.file) as f:
            niches.extend(line.strip() for line in f if line.strip())

    if not niches:
        print("error: specify --niches or --file", file=sys.stderr)
        return 1

    all_results = []
    for niche in niches:
        results = discover(
            niche=niche,
            near=args.near,
            radius_m=args.radius,
            limit=args.limit,
        )
        all_results.extend(results)

    save_results(all_results, args.output, args.format, args.verbose)
    return 0


def _cmd_list_sources() -> int:
    print("Available lead sources:")
    print("  overpass   OpenStreetMap Overpass API — free, unlimited, no key")
    return 0


def _cmd_list_niches() -> int:
    print("Supported business niches:")
    for n in ["roofing", "hvac", "plumbing", "electrical",
              "pest_control", "landscaping", "solar", "general"]:
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
