"""biz-factory: 'factory room' from the space-station blueprint.

Spawns N parallel micro-verticals (one per niche/metro combo), tracks
each as independent revenue stream with KPI, persists to hub.

Each vertical:
  - has its own state (cold / warming / hot / dead)
  - runs `empire-leads discover` for fresh leads on schedule
  - tracks leads_found, leads_replied, leads_won, revenue, cost
  - writes state to hub /v1/verticals (REST PUT)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Vertical:
    id: str
    niche: str
    metro: str
    state: str = "cold"  # cold / warming / hot / dead
    created_at: float = field(default_factory=time.time)
    last_scan_at: float = 0.0
    leads_found: int = 0
    leads_replied: int = 0
    leads_won: int = 0
    revenue_usd: float = 0.0
    cost_usd: float = 0.0
    notes: str = ""

    @property
    def roi(self) -> float:
        if self.cost_usd <= 0:
            return 0.0
        return (self.revenue_usd - self.cost_usd) / self.cost_usd

    def to_dict(self) -> dict:
        d = asdict(self)
        d["roi"] = round(self.roi, 3)
        return d


def vertical_id(niche: str, metro: str) -> str:
    import hashlib
    raw = f"{niche.lower().strip()}|{metro.lower().strip()}"
    return "v_" + hashlib.sha1(raw.encode()).hexdigest()[:10]


def spawn_vertical(niche: str, metro: str, notes: str = "") -> Vertical:
    return Vertical(
        id=vertical_id(niche, metro),
        niche=niche,
        metro=metro,
        notes=notes,
    )


def list_active(verticals: list[Vertical]) -> list[Vertical]:
    return [v for v in verticals if v.state != "dead"]


def kill_vertical(v: Vertical, reason: str = "") -> Vertical:
    v.state = "dead"
    if reason:
        v.notes = (v.notes + " | killed: " + reason).strip(" |")
    return v


def update_kpi(v: Vertical, leads_found: int = 0, leads_replied: int = 0,
               leads_won: int = 0, revenue_usd: float = 0.0,
               cost_usd: float = 0.0) -> Vertical:
    v.leads_found += leads_found
    v.leads_replied += leads_replied
    v.leads_won += leads_won
    v.revenue_usd += revenue_usd
    v.cost_usd += cost_usd
    v.last_scan_at = time.time()
    return v


def derive_state(v: Vertical) -> str:
    """Auto-derive state from KPIs."""
    if v.state == "dead":
        return "dead"
    if v.leads_won >= 3 and v.roi > 0.5:
        return "hot"
    if v.leads_found >= 5 and v.leads_replied >= 1:
        return "warming"
    if v.cost_usd > 50 and v.revenue_usd == 0 and v.leads_replied == 0:
        return "dead"  # burned cash with no traction
    return v.state


def sync_to_hub(v: Vertical, hub_url: str = "http://10.118.155.218:8081") -> bool:
    """Persist vertical state to hub. Returns True on 2xx."""
    url = f"{hub_url}/v1/verticals/{v.id}"
    data = json.dumps(v.to_dict()).encode()
    req = urllib.request.Request(url, data=data, method="PUT",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return 200 <= r.status < 300
    except Exception as e:
        log.warning("hub sync fail %s: %s", v.id, e)
        return False


def load_local(path: str = "/root/feedback/verticals.jsonl") -> list[Vertical]:
    """Load verticals from local JSONL (fallback when hub unreachable)."""
    verticals = []
    if not os.path.exists(path):
        return verticals
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                verticals.append(Vertical(**{k: v for k, v in d.items() if k != "roi"}))
            except Exception as e:
                log.warning("skip bad vertical line: %s", e)
    return verticals


def save_local(verticals: list[Vertical], path: str = "/root/feedback/verticals.jsonl") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for v in verticals:
            f.write(json.dumps(v.to_dict()) + "\n")
