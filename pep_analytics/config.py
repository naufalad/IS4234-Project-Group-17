"""Adjustable thresholds and weights for the transparent risk score.

Defaults mirror ``dataset2/README.md`` so that, under default config, the
recomputed ``risk_score`` matches the dataset's provided ``risk_score``
(see :func:`pep_analytics.scoring.score_report` and the sanity check in
``tests/``).

Requirements: 3.4 (adjustable configuration).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# Factor keys used throughout scoring. Keeping them as constants avoids typos
# between the weight table and the factor-emitting logic.
F_PASS_THROUGH = "pass_through"
F_VOLUME = "volume_vs_expected"
F_HIGH_RISK_DEST = "high_risk_destination"
F_PEP_NOT_FLAGGED = "pep_not_flagged"
F_SOF_UNVERIFIED = "source_of_funds_unverified"
F_OVERRIDE = "management_override"
F_CASH = "cash_deposits"


def default_weights() -> dict[str, int]:
    """Point weights per factor, per the dataset README risk table."""
    return {
        F_PASS_THROUGH: 25,
        F_VOLUME: 20,
        F_HIGH_RISK_DEST: 15,
        F_PEP_NOT_FLAGGED: 15,
        F_SOF_UNVERIFIED: 10,
        F_OVERRIDE: 15,
        F_CASH: 15,
    }


DEFAULT_WEIGHTS = default_weights()


@dataclass(frozen=True)
class RiskConfig:
    """Tunable parameters for scoring, exceptions, escalation and review.

    All fields have README-aligned defaults. The Streamlit sidebar builds an
    overridden copy via :meth:`with_overrides` so a supervisor can tune the
    model without code changes (Requirements 3.4, 3.5).
    """

    # --- risk factor thresholds (Requirement 3.1) ---
    pass_through_ratio_min: float = 0.8
    pass_through_inflow_min: float = 100_000.0
    volume_vs_expected_min: float = 5.0
    high_risk_dest_share_min: float = 0.5
    cash_min: float = 50_000.0

    # --- risk level bands (Requirement 3.2) ---
    medium_at: int = 30
    high_at: int = 60

    # --- weights (Requirement 3.1) ---
    weights: dict[str, int] = field(default_factory=default_weights)
    score_cap: int = 100

    # --- exception reporting (Requirement 5.1) ---
    sof_materiality_min: float = 100_000.0

    # --- escalation (Requirement 6) ---
    escalate_at: int = 60
    max_days_alert_to_sar: int = 90

    # --- independent KYC review (Requirement 7.3) ---
    kyc_review_interval_quarters: int = 4

    def with_overrides(self, **kwargs) -> "RiskConfig":
        """Return a copy with the given fields replaced, validated."""
        cfg = replace(self, **kwargs)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Guard against nonsensical config (Requirement: error handling)."""
        if not (0 <= self.escalate_at <= 100):
            raise ValueError("escalate_at must be between 0 and 100")
        if not (0 <= self.medium_at <= self.high_at <= 100):
            raise ValueError("risk bands must satisfy 0 <= medium_at <= high_at <= 100")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")
        if self.max_days_alert_to_sar < 0:
            raise ValueError("max_days_alert_to_sar must be non-negative")
        if self.kyc_review_interval_quarters < 1:
            raise ValueError("kyc_review_interval_quarters must be >= 1")
