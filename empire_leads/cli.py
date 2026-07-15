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

    # ── trend ("research lab") ────────────────────────────
    trend = sub.add_parser("trend", help="Score niches by market demand signal")
    trend.add_argument("niche", help="Business type to score")
    trend.add_argument("--metros", nargs="*", default=["Phoenix, AZ"],
                       help="Cities to score against")
    trend.add_argument("--sources", nargs="*", default=["reddit", "overpass", "craigslist"],
                       help="Signals to use")
    trend.add_argument("--output", "-o", default="", help="Output JSONL file")
    trend.add_argument("--quiet", "-q", action="store_true")

    # ── factory ("factory room") ──────────────────────────
    factory = sub.add_parser("factory", help="Spawn + manage micro-verticals")
    factory.add_argument("--spawn", nargs=2, metavar=("NICHE", "METRO"),
                         help="Spawn new vertical")
    factory.add_argument("--list", action="store_true", help="List all verticals")
    factory.add_argument("--kill", metavar="VERTICAL_ID", help="Kill vertical by ID")
    factory.add_argument("--scan", metavar="VERTICAL_ID",
                         help="Run discover for one vertical, update KPIs")
    factory.add_argument("--output", "-o", default="", help="Output file")

    # ── prune ("war room") ────────────────────────────────
    prune = sub.add_parser("prune", help="Daily portfolio review + auto-kill")
    prune.add_argument("--summary", action="store_true",
                       help="Print Telegram-ready summary")
    prune.add_argument("--output", "-o", default="", help="Decision log path")

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


def _cmd_trend(args: argparse.Namespace) -> int:
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    from .trend import score_trend
    results = score_trend(args.niche, args.metros, args.sources)
    out_path = args.output or ""
    import json as _json
    lines = [_json.dumps(t.to_dict()) for t in results]
    if out_path:
        with open(out_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"wrote {len(lines)} trends -> {out_path}")
    else:
        for line in lines:
            print(line)
    return 0


def _cmd_factory(args: argparse.Namespace) -> int:
    from .factory import (
        spawn_vertical, load_local, save_local, kill_vertical,
        update_kpi, sync_to_hub, vertical_id,
    )
    verticals = load_local()

    if args.spawn:
        niche, metro = args.spawn
        vid = vertical_id(niche, metro)
        if any(v.id == vid for v in verticals):
            print(f"already exists: {vid}")
            return 1
        v = spawn_vertical(niche, metro, notes="manually spawned")
        verticals.append(v)
        save_local(verticals)
        synced = sync_to_hub(v)
        print(f"spawned {vid} ({niche} @ {metro}) hub={'ok' if synced else 'fail'}")
        return 0

    if args.kill:
        for v in verticals:
            if v.id == args.kill:
                kill_vertical(v, reason="manual kill")
                save_local(verticals)
                sync_to_hub(v)
                print(f"killed {v.id}")
                return 0
        print(f"not found: {args.kill}")
        return 1

    if args.scan:
        from .engine import discover
        for v in verticals:
            if v.id == args.scan:
                r = discover(niche=v.niche, near=v.metro, limit_per_source=10)
                update_kpi(v, leads_found=len(r.leads))
                save_local(verticals)
                sync_to_hub(v)
                print(f"scanned {v.id} -> {len(r.leads)} new leads")
                return 0
        print(f"not found: {args.scan}")
        return 1

    # default: list
    import json as _json
    for v in verticals:
        print(_json.dumps(v.to_dict()))
    return 0


def _cmd_prune(args: argparse.Namespace) -> int:
    from .factory import load_local, save_local, sync_to_hub
    from .pruner import review_portfolio, summary_text
    verticals = load_local()
    decisions = review_portfolio(verticals)
    save_local(verticals)
    for v in verticals:
        sync_to_hub(v)
    if args.summary or not args.output:
        print(summary_text(decisions))
    if args.output:
        import json as _json
        with open(args.output, "w") as f:
            for d in decisions:
                f.write(_json.dumps(d.__dict__) + "\n")
        print(f"wrote {len(decisions)} decisions -> {args.output}")
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
    elif args.command == "trend":
        return _cmd_trend(args)
    elif args.command == "factory":
        return _cmd_factory(args)
    elif args.command == "prune":
        return _cmd_prune(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
