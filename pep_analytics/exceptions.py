"""Source-of-funds and compliance-override exception reporting.

Requirements: 5.1 (SoF gaps on material inflow), 5.2 (override against
compliance advice), 5.3 (introducer reliance), 5.4 (aggregate by bank/quarter).
"""
from __future__ import annotations

import pandas as pd

from pep_analytics.config import RiskConfig


def _is_yes(value) -> bool:
    return str(value).strip().lower() == "yes"


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def sof_exceptions(report: pd.DataFrame, cfg: RiskConfig | None = None) -> pd.DataFrame:
    """PEP client-quarters with unverified source of funds and material inflow."""
    cfg = cfg or RiskConfig()
    verified = report["source_of_funds_verified"].apply(_is_yes)
    inflow = _num(report, "inflow_usd")
    mask = (~verified) & (inflow > cfg.sof_materiality_min)
    cols = [c for c in ["quarter", "entity_id", "name", "swiss_bank",
                        "pep_category", "inflow_usd", "source_of_funds_verified",
                        "risk_score"] if c in report.columns]
    return report.loc[mask, cols].sort_values("inflow_usd", ascending=False)


def override_exceptions(report: pd.DataFrame) -> pd.DataFrame:
    """Management overrode a compliance exit/SAR recommendation (Requirement 5.2)."""
    override = _num(report, "management_overrides") >= 1
    recommended = _num(report, "compliance_recommended_exit_or_sar") >= 1
    mask = override & recommended
    cols = [c for c in ["quarter", "entity_id", "name", "swiss_bank",
                        "pep_category", "management_overrides",
                        "compliance_recommended_exit_or_sar", "sar_filed",
                        "risk_score"] if c in report.columns]
    return report.loc[mask, cols].sort_values("quarter")


def introducer_reliance(report: pd.DataFrame) -> pd.DataFrame:
    """Client-quarters that relied on an introducer vouching (Requirement 5.3)."""
    mask = _num(report, "introducer_assurance_used") >= 1
    cols = [c for c in ["quarter", "entity_id", "name", "swiss_bank",
                        "pep_category", "introducer_assurance_used",
                        "risk_score"] if c in report.columns]
    return report.loc[mask, cols].sort_values("quarter")


def aggregate_by_bank_quarter(report: pd.DataFrame, cfg: RiskConfig | None = None) -> pd.DataFrame:
    """Exception counts by Swiss bank and quarter to expose trends (Requirement 5.4)."""
    cfg = cfg or RiskConfig()
    df = report.copy()
    df["_sof"] = (~df["source_of_funds_verified"].apply(_is_yes)) & (
        _num(df, "inflow_usd") > cfg.sof_materiality_min
    )
    df["_override"] = (_num(df, "management_overrides") >= 1) & (
        _num(df, "compliance_recommended_exit_or_sar") >= 1
    )
    df["_introducer"] = _num(df, "introducer_assurance_used") >= 1
    agg = (
        df.groupby(["swiss_bank", "quarter"])[["_sof", "_override", "_introducer"]]
        .sum()
        .reset_index()
        .rename(columns={
            "_sof": "sof_exceptions",
            "_override": "override_exceptions",
            "_introducer": "introducer_reliance",
        })
    )
    return agg.sort_values(["swiss_bank", "quarter"]).reset_index(drop=True)
