"""portfolio-pruner: 'war room' from the space-station blueprint.

Daily review of all verticals. Decisions:
  - KILL   : ROI < 0 for 14d OR cost > $50 with 0 leads_replied
  - DOUBLE : ROI > 1.0 AND leads_won >= 5 (allocate more scan budget)
  - HOLD   : everything else

Outputs:
  - JSONL decision log per vertical
  - Summary text for Telegram push
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional

from .factory import Vertical, kill_vertical, derive_state

log = logging.getLogger(__name__)


@dataclass
class Decision:
    vertical_id: str
    niche: str
    metro: str
    action: str  # KILL / DOUBLE / HOLD / WARM
    reason: str
    roi: float
    revenue_usd: float
    cost_usd: float
    age_days: float
    decided_at: float = 0.0

    def __post_init__(self):
        if self.decided_at == 0.0:
            self.decided_at = time.time()


def _age_days(v: Vertical) -> float:
    return (time.time() - v.created_at) / 86400.0


def evaluate(v: Vertical) -> Decision:
    """Apply rules, return Decision. Mutates v if KILL."""
    age = _age_days(v)
    roi = v.roi

    # Rule 1: KILL — burned cash no traction
    if v.cost_usd >= 50 and v.leads_replied == 0 and age >= 7:
        kill_vertical(v, reason=f"burned ${v.cost_usd:.0f} no replies 7d")
        return Decision(
            vertical_id=v.id, niche=v.niche, metro=v.metro,
            action="KILL", reason=f"${v.cost_usd:.0f} spent, 0 replies, 7d+",
            roi=roi, revenue_usd=v.revenue_usd, cost_usd=v.cost_usd, age_days=age,
        )

    # Rule 2: KILL — sustained negative ROI
    if age >= 14 and roi < 0 and v.leads_won == 0:
        kill_vertical(v, reason=f"neg ROI {roi:.2f} for {age:.0f}d")
        return Decision(
            vertical_id=v.id, niche=v.niche, metro=v.metro,
            action="KILL", reason=f"neg ROI {age:.0f}d, no wins",
            roi=roi, revenue_usd=v.revenue_usd, cost_usd=v.cost_usd, age_days=age,
        )

    # Rule 3: DOUBLE — proven winners
    if roi >= 1.0 and v.leads_won >= 5:
        return Decision(
            vertical_id=v.id, niche=v.niche, metro=v.metro,
            action="DOUBLE", reason=f"ROI {roi:.1f}x, {v.leads_won} wins",
            roi=roi, revenue_usd=v.revenue_usd, cost_usd=v.cost_usd, age_days=age,
        )

    # Rule 4: WARM — getting traction, not yet profitable
    if v.leads_replied >= 1 and v.leads_won == 0 and age >= 7:
        return Decision(
            vertical_id=v.id, niche=v.niche, metro=v.metro,
            action="WARM", reason=f"{v.leads_replied} replies, no wins yet",
            roi=roi, revenue_usd=v.revenue_usd, cost_usd=v.cost_usd, age_days=age,
        )

    # Default: HOLD
    return Decision(
        vertical_id=v.id, niche=v.niche, metro=v.metro,
        action="HOLD", reason=f"age {age:.0f}d, monitoring",
        roi=roi, revenue_usd=v.revenue_usd, cost_usd=v.cost_usd, age_days=age,
    )


def review_portfolio(verticals: list[Vertical]) -> list[Decision]:
    """Run evaluate() across all verticals. Returns decision list."""
    decisions = []
    for v in verticals:
        if v.state == "dead":
            continue  # don't re-evaluate corpses
        decisions.append(evaluate(v))
    return decisions


def summary_text(decisions: list[Decision]) -> str:
    """Telegram-ready summary."""
    if not decisions:
        return "War Room: no active verticals."

    by_action = {"KILL": [], "DOUBLE": [], "WARM": [], "HOLD": []}
    for d in decisions:
        by_action[d.action].append(d)

    total_rev = sum(d.revenue_usd for d in decisions)
    total_cost = sum(d.cost_usd for d in decisions)
    portfolio_roi = (total_rev - total_cost) / total_cost if total_cost > 0 else 0

    lines = [
        f"War Room brief — {len(decisions)} verticals",
        f"Portfolio: ${total_rev:.0f} rev / ${total_cost:.0f} cost = {portfolio_roi:.2f}x ROI",
        "",
    ]
    if by_action["DOUBLE"]:
        lines.append(f"DOUBLE ({len(by_action['DOUBLE'])}):")
        for d in by_action["DOUBLE"][:5]:
            lines.append(f"  + {d.niche} @ {d.metro} — {d.reason}")
    if by_action["WARM"]:
        lines.append(f"WARM ({len(by_action['WARM'])}):")
        for d in by_action["WARM"][:5]:
            lines.append(f"  ~ {d.niche} @ {d.metro} — {d.reason}")
    if by_action["KILL"]:
        lines.append(f"KILL ({len(by_action['KILL'])}):")
        for d in by_action["KILL"][:5]:
            lines.append(f"  x {d.niche} @ {d.metro} — {d.reason}")
    if by_action["HOLD"]:
        lines.append(f"HOLD: {len(by_action['HOLD'])} verticals steady")

    return "\n".join(lines)
