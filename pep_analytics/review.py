"""Independent KYC-review worklist for PEP accounts (Jyske-bank reference).

Requirements: 7.1 (seeded by blind spots + hidden edges), 7.2 (PEPs + close
associates + PEP-owned companies), 7.3 (configurable refresh interval),
7.4 (prioritised by risk/exposure).
"""
from __future__ import annotations

import pandas as pd

from pep_analytics.config import RiskConfig
from pep_analytics.graph import PEP_LINKED_CATEGORIES


def _is_yes(value) -> bool:
    return str(value).strip().lower() == "yes"


def _is_no(value) -> bool:
    return str(value).strip().lower() == "no"


def _quarter_index(q: str) -> int:
    """Convert '2002Q3' to an integer ordinal for interval maths."""
    try:
        year, quarter = q.split("Q")
        return int(year) * 4 + (int(quarter) - 1)
    except Exception:
        return 0


def review_worklist(
    entities: pd.DataFrame,
    edges: pd.DataFrame,
    scored_report: pd.DataFrame,
    cfg: RiskConfig | None = None,
) -> pd.DataFrame:
    """Build the prioritised independent-review worklist.

    One row per PEP-linked entity, annotated with the signals that justify a
    review and a ``due_for_refresh`` flag derived from the review interval.
    """
    cfg = cfg or RiskConfig()

    # Scope: PEPs, PEP family, close associates, PEP-owned companies (Req 7.2).
    pop = entities[entities["pep_category"].isin(PEP_LINKED_CATEGORIES)].copy()

    # Blind spots: PEP-linked but not flagged by the bank (Req 7.1 seed).
    pop["is_blind_spot"] = ~pop["flagged_as_pep_by_bank"].apply(_is_yes)

    # Hidden edges touching each entity (Req 7.1 seed).
    hidden = edges[edges["known_to_bank"].apply(_is_no)]
    hidden_entities = set(hidden["source_id"]).union(set(hidden["target_id"]))
    pop["has_hidden_link"] = pop["entity_id"].isin(hidden_entities)

    # Peak risk and most-recent active quarter from the scored report.
    if not scored_report.empty:
        grp = scored_report.groupby("entity_id")
        peak_risk = grp["risk_score"].max()
        last_q = grp["quarter"].max()
        pop["max_risk_score"] = pop["entity_id"].map(peak_risk).fillna(0.0)
        pop["last_active_quarter"] = pop["entity_id"].map(last_q)
        latest_overall = scored_report["quarter"].map(_quarter_index).max()
    else:
        pop["max_risk_score"] = 0.0
        pop["last_active_quarter"] = pd.NA
        latest_overall = 0

    # Due for refresh when the last activity is older than the review interval
    # (Req 7.3). Entities with no reporting history are treated as due.
    def _due(q) -> bool:
        if pd.isna(q):
            return True
        return (latest_overall - _quarter_index(q)) >= cfg.kyc_review_interval_quarters

    pop["due_for_refresh"] = pop["last_active_quarter"].apply(_due)

    # Priority = risk + explicit boosts for the seeding signals (Req 7.4).
    pop["priority_score"] = (
        pop["max_risk_score"]
        + pop["is_blind_spot"].astype(int) * 20
        + pop["has_hidden_link"].astype(int) * 25
    )

    cols = [
        "entity_id", "name", "pep_category", "linked_pep_name", "swiss_bank",
        "flagged_as_pep_by_bank", "is_blind_spot", "has_hidden_link",
        "max_risk_score", "last_active_quarter", "due_for_refresh",
        "priority_score",
    ]
    cols = [c for c in cols if c in pop.columns]
    return pop[cols].sort_values("priority_score", ascending=False).reset_index(drop=True)
