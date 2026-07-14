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


def print_results(results: list[ScanResult], verbose: bool = False) -> None:
    """Pretty-print scan results to terminal."""
    total_leads = sum(len(r.leads) for r in results)
    total_errors = sum(1 for r in results if r.error)
    print(f"\n── Results: {total_leads} leads from {len(results)} scans ({total_errors} errors) ──")

    for r in results:
        if r.error:
            print(f"  ✗ {r.source}/{r.niche}: {r.error}")
        elif r.leads:
            print(f"  ✓ {r.source}/{r.niche}: {len(r.leads)} leads in {r.elapsed_seconds:.1f}s")
            if verbose:
                for lead in r.leads[:5]:
                    print(f"      {lead.name[:50]:50s} | {lead.phone[:16]:16s} | {lead.city[:12]}")
                if len(r.leads) > 5:
                    print(f"      ... and {len(r.leads) - 5} more")
        else:
            print(f"  ∼ {r.source}/{r.niche}: 0 leads in {r.elapsed_seconds:.1f}s")
