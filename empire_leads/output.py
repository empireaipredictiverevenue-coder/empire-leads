"""Output writers — JSONL, CSV, terminal."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import TextIO

from .models import Lead, ScanResult


def write_jsonl(leads: list[Lead], path: str | Path, append: bool = False) -> int:
    """Write leads as JSONL (one JSON object per line). Returns count."""
    mode = "a" if append else "w"
    count = 0
    with open(path, mode, encoding="utf-8") as f:
        for lead in leads:
            f.write(lead.to_jsonl() + "\n")
            count += 1
    return count


def write_csv(leads: list[Lead], path: str | Path, append: bool = False) -> int:
    """Write leads as CSV. Returns count."""
    mode = "a" if append else "w"
    if not leads:
        return 0
    fields = list(leads[0].to_dict().keys())
    count = 0
    with open(path, mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not append:
            writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_dict())
            count += 1
    return count


def print_result(result: ScanResult, verbose: bool = False) -> None:
    """Pretty-print a single ScanResult to terminal."""
    r = result
    print(f"\n── Results: {r.total_found} found, {r.total_deduped} deduped in {r.time_s}s ──")

    for src, src_result in (r.results or {}).items():
        count = src_result.get("leads", 0)
        elapsed = src_result.get("time_s", 0)
        error = src_result.get("error")
        if error:
            print(f"  ✗ {src}: {error}")
        elif count:
            print(f"  ✓ {src}: {count} leads in {elapsed}s")
        else:
            print(f"  ∼ {src}: 0 leads in {elapsed}s")

    if r.leads and verbose:
        print()
        for lead in r.leads[:5]:
            phone = (lead.phone or "")[:16]
            city = (lead.city or lead.state or "")[:12]
            src = lead.source or ""
            print(f"  {lead.name[:48]:48s} | {phone:16s} | {city:12s} | {src}")
        if len(r.leads) > 5:
            print(f"  ... and {len(r.leads) - 5} more")

    elif r.leads and not verbose:
        print(f"\n  {len(r.leads)} leads. Use --verbose for details.\n")


def save_results(result: ScanResult, output_path: str, fmt: str = "jsonl",
                 verbose: bool = False) -> int:
    """Save results to file and/or print summary."""
    if output_path:
        path = Path(output_path)
        if fmt == "jsonl":
            count = write_jsonl(result.leads, path)
        else:
            count = write_csv(result.leads, path)
        print(f"Saved {count} leads to {path}", file=sys.stderr)
    else:
        print_result(result, verbose)

    return 0 if result.leads else 1
