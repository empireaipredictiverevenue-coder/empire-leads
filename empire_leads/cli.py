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

    # ── public-apis (source factory) ──────────────────────
    pa = sub.add_parser("public-apis",
                        help="List/generate/run sources from public-apis repo")
    pa_sub = pa.add_subparsers(dest="pa_command", required=True)

    pa_list = pa_sub.add_parser("list", help="List catalog entries")
    pa_list.add_argument("--category", action="append", help="Filter by category")
    pa_list.add_argument("--auth", help='Filter by auth (e.g. "No", "apiKey")')
    pa_list.add_argument("--https-only", action="store_true", default=True)
    pa_list.add_argument("--cors-yes-only", action="store_true")
    pa_list.add_argument("--keyword", help="Search name + description")
    pa_list.add_argument("--limit", type=int, default=50, help="Max entries to show")
    pa_list.add_argument("--categories-only", action="store_true",
                         help="Just list category names + counts")

    pa_gen = pa_sub.add_parser("generate",
                               help="Generate source skeletons from catalog")
    pa_gen.add_argument("--category", action="append")
    pa_gen.add_argument("--auth", default="No")
    pa_gen.add_argument("--https-only", type=bool, default=True)
    pa_gen.add_argument("--keyword", help="Search keyword")
    pa_gen.add_argument("--max", type=int, default=20,
                        help="Cap entries to generate (avoid runaway)")

    pa_run = pa_sub.add_parser("run", help="Run a generated source by slug")
    pa_run.add_argument("slug", help="Source slug, e.g. cat_facts")
    pa_run.add_argument("--niche", default="general")
    pa_run.add_argument("--limit", type=int, default=20)

    pa_ls = pa_sub.add_parser("ls-generated",
                              help="List already-generated source files")

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


def _cmd_public_apis(args: argparse.Namespace) -> int:
    from .sources.public_apis import (
        get_catalog, filter_catalog, generate, discover,
        list_categories, list_generated,
    )
    if args.pa_command == "list":
        catalog = get_catalog()
        if args.categories_only:
            cats = list_categories(catalog)
            for c, n in cats.items():
                print(f"  {c:30s} {n}")
            return 0
        entries = filter_catalog(
            catalog,
            categories=args.category,
            auth=args.auth,
            https_only=args.https_only,
            cors_yes_only=args.cors_yes_only,
            keyword=args.keyword,
        )
        for e in entries[: args.limit]:
            print(f"  [{e.category:20s}] {e.name:35s} auth={e.auth:12s} "
                  f"https={int(e.https)} cors={e.cors:7s} {e.url}")
        print(f"\n({len(entries)} entries, {len(entries[: args.limit])} shown)")
        return 0

    if args.pa_command == "generate":
        catalog = get_catalog()
        entries = filter_catalog(
            catalog,
            categories=args.category,
            auth=args.auth,
            https_only=args.https_only,
            keyword=args.keyword,
        )[: args.max]
        if not entries:
            print("no entries matched")
            return 1
        from .sources.public_apis.generator import generate_many
        paths = generate_many(entries)
        for p in paths:
            print(f"  wrote {p.name}")
        print(f"\nGenerated {len(paths)} source files")
        return 0

    if args.pa_command == "run":
        try:
            leads = discover(args.slug, niche=args.niche, limit=args.limit)
        except FileNotFoundError as e:
            print(f"error: {e}")
            return 1
        import json as _json
        for lead in leads:
            print(_json.dumps(lead.to_dict(), default=str))
        print(f"\n({len(leads)} leads)")
        return 0

    if args.pa_command == "ls-generated":
        for p in list_generated():
            print(f"  {p.stem}")
        return 0

    return 1


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
    elif args.command == "public-apis":
        return _cmd_public_apis(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
