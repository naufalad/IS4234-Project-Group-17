"""Transparent, adjustable 0-100 risk score for PEP client-quarters.

Implements the README risk table exactly, driven by :class:`RiskConfig` so
thresholds and weights are tunable. Every row gets a ``score_factors`` list of
``(factor, points)`` tuples so the score is fully explainable (Requirement 3.6).

The score uses ONLY input signals. It never reads ``is_suspicious``,
``scenario`` or ``typology`` (Requirement 3.3).
"""
from __future__ import annotations

import pandas as pd

from pep_analytics import config as C
from pep_analytics.config import RiskConfig


def _is_yes(value) -> bool:
    return str(value).strip().lower() == "yes"


def _row_factors(row: pd.Series, cfg: RiskConfig) -> list[tuple[str, int]]:
    """Return the (factor, points) contributions that fire for one row.

    Mirrors the README table:
      - pass_through_ratio >= 0.8 AND inflow > 100k  -> 25
      - volume_vs_expected > 5                        -> 20
      - high_risk_destination_share > 0.5             -> 15
      - PEP-linked but not flagged by bank            -> 15
      - source of funds not verified                  -> 10
      - management override this quarter              -> 15
      - cash deposits > 50k                           -> 15
    """
    w = cfg.weights
    factors: list[tuple[str, int]] = []

    inflow = float(row.get("inflow_usd") or 0)
    ratio = row.get("pass_through_ratio")
    ratio = float(ratio) if pd.notna(ratio) else 0.0
    if ratio >= cfg.pass_through_ratio_min and inflow > cfg.pass_through_inflow_min:
        factors.append((C.F_PASS_THROUGH, w[C.F_PASS_THROUGH]))

    vol = row.get("volume_vs_expected")
    vol = float(vol) if pd.notna(vol) else 0.0
    if vol > cfg.volume_vs_expected_min:
        factors.append((C.F_VOLUME, w[C.F_VOLUME]))

    dest = row.get("high_risk_destination_share")
    dest = float(dest) if pd.notna(dest) else 0.0
    if dest > cfg.high_risk_dest_share_min:
        factors.append((C.F_HIGH_RISK_DEST, w[C.F_HIGH_RISK_DEST]))

    # PEP-linked but not flagged by the bank. Every row in the quarterly report
    # is PEP-linked by construction, so the test is simply "not flagged".
    if not _is_yes(row.get("flagged_as_pep_by_bank")):
        factors.append((C.F_PEP_NOT_FLAGGED, w[C.F_PEP_NOT_FLAGGED]))

    if not _is_yes(row.get("source_of_funds_verified")):
        factors.append((C.F_SOF_UNVERIFIED, w[C.F_SOF_UNVERIFIED]))

    override = row.get("management_overrides")
    override = float(override) if pd.notna(override) else 0.0
    if override >= 1:
        factors.append((C.F_OVERRIDE, w[C.F_OVERRIDE]))

    cash = float(row.get("cash_usd") or 0)
    if cash > cfg.cash_min:
        factors.append((C.F_CASH, w[C.F_CASH]))

    return factors


def risk_level(score: int, cfg: RiskConfig) -> str:
    """Map a score to Low / Medium / High per the configured bands."""
    if score >= cfg.high_at:
        return "High"
    if score >= cfg.medium_at:
        return "Medium"
    return "Low"


def score_report(report: pd.DataFrame, cfg: RiskConfig | None = None) -> pd.DataFrame:
    """Return a copy of ``report`` with recomputed risk columns.

    Adds (overwriting any dataset-provided values so the model is independent):
      - ``risk_score``       : capped 0-100 integer
      - ``risk_level``       : Low / Medium / High
      - ``escalate_to_finma``: "Yes"/"No" at the configured escalation level
      - ``score_factors``    : list of (factor, points) that fired
    """
    cfg = cfg or RiskConfig()
    df = report.copy()

    factors = df.apply(lambda r: _row_factors(r, cfg), axis=1)
    raw = factors.apply(lambda fs: sum(p for _, p in fs))
    scores = raw.clip(upper=cfg.score_cap).astype(int)

    df["score_factors"] = factors
    df["risk_score"] = scores
    df["risk_level"] = scores.apply(lambda s: risk_level(int(s), cfg))
    df["escalate_to_finma"] = (scores >= cfg.escalate_at).map({True: "Yes", False: "No"})
    return df
