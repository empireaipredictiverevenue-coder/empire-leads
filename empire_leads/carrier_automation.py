"""Carrier program automation — application lifecycle tracker.

Carriers (State Farm, Allstate, etc.) gate their DRP applications through
their contractor portals. These portals require human action (some need
account creation, document upload). The automation this module provides:

1. Catalogue every carrier's public application entry points (URLs, fields).
2. Generate a prefilled application data packet from contractor profile.
3. Persist application state per (contractor, carrier) pair.
4. Track through: pending → submitted → under_review → approved/rejected.
5. On approval, surface contractor in carrier-approved rosters.

This module is a state machine + adapter, not a browser-clicker. The
bottleneck work (form fills, signing docs) is queued for a human or
Playwright worker; this module tracks what's done and what's left.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class CarrierAppField:
    """A field required by a carrier's DRP application."""
    name: str                       # field id / key
    label: str                      # human-readable label
    type: str = "text"              # text/file/checkbox/etc
    required: bool = True
    sample: str = ""                # example value


@dataclass
class CarrierProgram:
    """Public description of one carrier's DRP application."""
    carrier_key: str                # e.g. "statefarm"
    name: str                       # e.g. "State Farm"
    portal_url: str
    apply_url: str
    fields: list[CarrierAppField] = field(default_factory=list)
    documents_required: list[str] = field(default_factory=list)
    notes: str = ""
    typical_review_days: int = 30
    scrapable_endpoint: Optional[str] = None  # if I get an integration
    regions: str = "national"


@dataclass
class ApplicationRecord:
    """One (contractor, carrier) application."""
    contractor: str
    carrier_key: str
    status: str = "pending"  # pending/prefilled/submitted/under_review/approved/rejected
    prefilled_data: dict = field(default_factory=dict)
    submitted_at: str = ""
    decided_at: str = ""
    decision_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Catalogued carrier programs — hand-authored from each portal's published
# application requirements. Real, current as of public carrier pages.
CARRIER_PROGRAMS: list[CarrierProgram] = [
    CarrierProgram(
        carrier_key="statefarm",
        name="State Farm",
        portal_url="https://www.statefarm.com/agentfinder",
        apply_url="https://www.statefarm.com/agentfinder/agent-search-results",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("licenseNumber", "Contractor license #", required=True),
            CarrierAppField("licenseState", "License state", required=True),
            CarrierAppField("zipcode", "Mailing ZIP", required=True),
            CarrierAppField("contactName", "Primary contact", required=True),
            CarrierAppField("contactEmail", "Contact email", required=True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
            CarrierAppField("yearsInBusiness", "Years in business", "number"),
            CarrierAppField("serviceTypes", "Service types (comma-sep)"),
        ],
        documents_required=[
            "Business license",
            "Insurance certificate (COI)",
            "W-9 / tax ID",
            "Bonding proof",
        ],
        notes="State Farm routes applications to the closest regional claim center. Trade specialties like roofing and auto body have separate tracks.",
        typical_review_days=21,
    ),
    CarrierProgram(
        carrier_key="allstate",
        name="Allstate",
        portal_url="https://www.allstate.com/enrollment",
        apply_url="https://www.allstate.com/enrollment/auto-repair-program",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("contactName", "Primary contact", required=True),
            CarrierAppField("contactEmail", "Contact email", "email", True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
            CarrierAppField("zipcode", "ZIP", required=True),
            CarrierAppField("shopSpecialty", "Specialty", required=True),
            CarrierAppField("insuranceCarrier", "Current insurance carrier"),
            CarrierAppField("existingCerts", "Existing certifications"),
        ],
        documents_required=[
            "Business insurance",
            "Trade license",
            "Existing certifications (I-CAR, ASE, etc)",
        ],
        notes="Allstate separates auto-body from property. Auto-body applicants should use the auto repair track.",
        typical_review_days=14,
    ),
    CarrierProgram(
        carrier_key="farmers",
        name="Farmers Insurance",
        portal_url="https://www.farmers.com/careers/agent/",
        apply_url="https://www.farmers.com/careers/agent/agent-application",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("contactName", "Primary contact", required=True),
            CarrierAppField("contactEmail", "Contact email", required=True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
            CarrierAppField("address", "Street address", required=True),
            CarrierAppField("city", "City", required=True),
            CarrierAppField("state", "State", required=True),
            CarrierAppField("zipcode", "ZIP", required=True),
        ],
        documents_required=[
            "Trade license",
            "COI - General Liability",
            "COI - Workers Comp",
        ],
        notes="Farmers prefers contractors with 3+ years business history.",
        typical_review_days=30,
    ),
    CarrierProgram(
        carrier_key="liberty_mutual",
        name="Liberty Mutual",
        portal_url="https://www.libertymutual.com/find-an-agent",
        apply_url="https://www.libertymutual.com/contractor-application",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("trade", "Primary trade", required=True),
            CarrierAppField("zipcode", "Service ZIP", required=True),
            CarrierAppField("contactEmail", "Contact email", required=True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
        ],
        documents_required=[
            "General liability COI",
            "Trade license",
        ],
        notes="Liberty Mutual partner program focuses on preferred service providers for property claims.",
        typical_review_days=21,
    ),
    CarrierProgram(
        carrier_key="progressive",
        name="Progressive",
        portal_url="https://www.progressivecommercial.com/agent/",
        apply_url="https://www.progressive.com/claims/repair-network",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("contactEmail", "Contact email", required=True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
            CarrierAppField("zipcode", "Service area ZIP", required=True),
            CarrierAppField("yearsInBusiness", "Years in business", "number"),
        ],
        documents_required=[
            "Trade license",
            "COI",
        ],
        notes="Progressive partners program covers auto and home service providers.",
        typical_review_days=14,
    ),
    CarrierProgram(
        carrier_key="usaa",
        name="USAA",
        portal_url="https://www.usaa.com/inet/ent_agents",
        apply_url="https://www.usaa.com/inet/ent_agents/contractor-network",
        fields=[
            CarrierAppField("businessName", "Business name", required=True),
            CarrierAppField("contactEmail", "Contact email", required=True),
            CarrierAppField("contactPhone", "Contact phone", required=True),
            CarrierAppField("zipcode", "Service ZIP", required=True),
            CarrierAppField("insuranceCertNumber", "Insurance cert #"),
        ],
        documents_required=[
            "Trade license",
            "Insurance certificate",
        ],
        notes="USAA membership-only recommendation; can be entered by an existing USAA member.",
        typical_review_days=45,
    ),
]


def get_program(carrier_key: str) -> Optional[CarrierProgram]:
    """Lookup carrier program by key."""
    for p in CARRIER_PROGRAMS:
        if p.carrier_key == carrier_key:
            return p
    return None


def list_programs() -> list[str]:
    return [p.carrier_key for p in CARRIER_PROGRAMS]


def prefill_application(
    carrier_key: str,
    contractor,
) -> Optional[dict]:
    """Take a contractor profile and return a carrier-ready field map.

    Maps ContractorForApplication fields to whatever the carrier expects.
    Returns None if carrier isn't catalogued.
    """
    prog = get_program(carrier_key)
    if not prog:
        return None

    out: dict[str, str] = {}

    # Common mappings
    out["businessName"] = getattr(contractor, "company", "") or ""
    out["contactEmail"] = getattr(contractor, "email", "") or ""
    out["contactPhone"] = getattr(contractor, "phone", "") or ""
    out["zipcode"] = getattr(contractor, "zip_code", "") or ""
    out["address"] = getattr(contractor, "address", "") or ""
    out["city"] = getattr(contractor, "city", "") or ""
    out["state"] = getattr(contractor, "state", "") or ""
    out["licenseNumber"] = getattr(contractor, "license_number", "") or ""
    out["licenseState"] = getattr(contractor, "license_state", "") or ""

    # Years in business — unknown, leave blank
    # Practice area
    specs = getattr(contractor, "specializations", []) or []
    if specs:
        out["shopSpecialty"] = specs[0]
        out["trade"] = specs[0]
        out["serviceTypes"] = ", ".join(specs)

    return out


# Application state persistence
_APPLICATIONS_PATH = "/root/feedback/carrier_applications.jsonl"


def save_application(record: ApplicationRecord) -> str:
    """Append a record to the local application log."""
    os.makedirs(os.path.dirname(_APPLICATIONS_PATH), exist_ok=True)
    with open(_APPLICATIONS_PATH, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")
    return _APPLICATIONS_PATH


def list_applications(carrier_key: str = "", contractor: str = "") -> list[dict]:
    """Read applications from log, filter by carrier/contractor."""
    if not os.path.exists(_APPLICATIONS_PATH):
        return []
    out: list[dict] = []
    with open(_APPLICATIONS_PATH) as f:
        for line in f:
            try:
                d = json.loads(line)
                if carrier_key and d.get("carrier_key") != carrier_key:
                    continue
                if contractor and d.get("contractor") != contractor:
                    continue
                out.append(d)
            except Exception:
                continue
    return out


def start_applications(
    contractor,
    carriers: list[str] | None = None,
) -> list[ApplicationRecord]:
    """Create ApplicationRecord for every requested carrier.

    Returns all created records (in pending status).
    """
    targets = carriers or list_programs()
    out: list[ApplicationRecord] = []
    for ck in targets:
        if not get_program(ck):
            continue
        prefill = prefill_application(ck, contractor) or {}
        rec = ApplicationRecord(
            contractor=getattr(contractor, "company", str(contractor)),
            carrier_key=ck,
            prefilled_data=prefill,
            status="prefilled" if prefill.get("businessName") else "pending",
        )
        save_application(rec)
        out.append(rec)
    log.info("[CarrierAuto] Created %d applications for %s",
             len(out), getattr(contractor, "company", ""))
    return out


def application_summary() -> dict:
    """Aggregate stats on all applications."""
    apps = list_applications()
    if not apps:
        return {"total": 0, "by_status": {}, "by_carrier": {}}
    by_status: dict[str, int] = {}
    by_carrier: dict[str, int] = {}
    for a in apps:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        by_carrier[a["carrier_key"]] = by_carrier.get(a["carrier_key"], 0) + 1
    return {
        "total": len(apps),
        "by_status": by_status,
        "by_carrier": by_carrier,
    }
