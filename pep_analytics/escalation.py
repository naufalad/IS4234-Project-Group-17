"""Automated escalation to FINMA on threshold breach.

Requirements: 6.1 (score threshold), 6.2 (SAR-delay trigger), 6.3 (record
fields), 6.4 (no manual gate), 6.5 (export).
"""
from __future__ import annotations

import pandas as pd

from pep_analytics.config import RiskConfig


def _factors_text(factors) -> str:
    if not isinstance(factors, (list, tuple)):
        return ""
    return ", ".join(f"{name} (+{pts})" for name, pts in factors)


def build_escalations(scored: pd.DataFrame, cfg: RiskConfig | None = None) -> pd.DataFrame:
    """One escalation record per breaching client-quarter.

    Triggers (either fires, no manual approval step):
      - risk_score >= cfg.escalate_at
      - days_alert_to_sar > cfg.max_days_alert_to_sar
    """
    cfg = cfg or RiskConfig()
    df = scored.copy()

    score = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0)
    days = pd.to_numeric(df.get("days_alert_to_sar"), errors="coerce").fillna(0)

    score_trigger = score >= cfg.escalate_at
    sar_trigger = days > cfg.max_days_alert_to_sar
    breaching = score_trigger | sar_trigger

    def reason(i: int) -> str:
        parts = []
        if score_trigger.iloc[i]:
            parts.append(f"risk_score {int(score.iloc[i])} >= {cfg.escalate_at}")
        if sar_trigger.iloc[i]:
            parts.append(
                f"SAR delay {int(days.iloc[i])}d > {cfg.max_days_alert_to_sar}d"
            )
        return "; ".join(parts)

    out = df.loc[breaching].copy().reset_index(drop=True)
    if out.empty:
        return pd.DataFrame(columns=[
            "entity_id", "name", "quarter", "swiss_bank", "pep_category",
            "flagged_as_pep_by_bank", "risk_score", "risk_level",
            "trigger_reason", "factors",
        ])

    out["trigger_reason"] = [reason(i) for i in range(len(out))]
    out["factors"] = out["score_factors"].apply(_factors_text) if "score_factors" in out.columns else ""

    cols = [c for c in [
        "entity_id", "name", "quarter", "swiss_bank", "pep_category",
        "flagged_as_pep_by_bank", "risk_score", "risk_level",
        "trigger_reason", "factors",
    ] if c in out.columns]
    return out[cols].sort_values(["risk_score", "quarter"], ascending=[False, True]).reset_index(drop=True)


def to_csv(escalations: pd.DataFrame) -> bytes:
    """Serialise escalation records to CSV bytes for download (Requirement 6.5)."""
    return escalations.to_csv(index=False).encode("utf-8")
