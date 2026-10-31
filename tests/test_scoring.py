"""Unit tests for the transparent risk score (Requirements 3.1, 3.2, 3.5).

Run with:  pytest
Requires pandas (see requirements.txt).
"""
import pandas as pd
import pytest

from pep_analytics import config as C
from pep_analytics.config import RiskConfig
from pep_analytics.data_loader import load_all
from pep_analytics.scoring import risk_level, score_report


def _row(**over):
    base = dict(
        inflow_usd=0.0, outflow_usd=0.0, cash_usd=0.0, pass_through_ratio=0.0,
        volume_vs_expected=0.0, high_risk_destination_share=0.0,
        flagged_as_pep_by_bank="Yes", source_of_funds_verified="Yes",
        management_overrides=0, quarter="2002Q1", entity_id="E1", name="X",
        swiss_bank="CH_A", pep_category="PEP", is_suspicious="No",
        days_alert_to_sar=0,
    )
    base.update(over)
    return base


def test_each_factor_fires_with_expected_points():
    cfg = RiskConfig()
    cases = {
        C.F_PASS_THROUGH: _row(pass_through_ratio=0.9, inflow_usd=200_000),
        C.F_VOLUME: _row(volume_vs_expected=6),
        C.F_HIGH_RISK_DEST: _row(high_risk_destination_share=0.6),
        C.F_PEP_NOT_FLAGGED: _row(flagged_as_pep_by_bank="No"),
        C.F_SOF_UNVERIFIED: _row(source_of_funds_verified="No"),
        C.F_OVERRIDE: _row(management_overrides=1),
        C.F_CASH: _row(cash_usd=60_000),
    }
    for factor, row in cases.items():
        out = score_report(pd.DataFrame([row]), cfg)
        assert out.iloc[0]["risk_score"] == cfg.weights[factor], factor
        fired = [f for f, _ in out.iloc[0]["score_factors"]]
        assert fired == [factor], factor


def test_pass_through_requires_both_ratio_and_inflow():
    cfg = RiskConfig()
    # High ratio but low inflow -> factor must NOT fire.
    out = score_report(pd.DataFrame([_row(pass_through_ratio=0.95, inflow_usd=1_000)]), cfg)
    assert out.iloc[0]["risk_score"] == 0


def test_score_is_capped_at_100():
    cfg = RiskConfig()
    row = _row(
        pass_through_ratio=1.0, inflow_usd=1_000_000, volume_vs_expected=10,
        high_risk_destination_share=0.9, flagged_as_pep_by_bank="No",
        source_of_funds_verified="No", management_overrides=2, cash_usd=100_000,
    )
    out = score_report(pd.DataFrame([row]), cfg)
    assert out.iloc[0]["risk_score"] == 100  # raw would be 115


def test_risk_level_bands():
    cfg = RiskConfig()
    assert risk_level(0, cfg) == "Low"
    assert risk_level(29, cfg) == "Low"
    assert risk_level(30, cfg) == "Medium"
    assert risk_level(59, cfg) == "Medium"
    assert risk_level(60, cfg) == "High"


def test_answer_key_not_used():
    """Changing is_suspicious must not change the score (Requirement 3.3)."""
    cfg = RiskConfig()
    a = score_report(pd.DataFrame([_row(is_suspicious="No", management_overrides=1)]), cfg)
    b = score_report(pd.DataFrame([_row(is_suspicious="Yes", management_overrides=1)]), cfg)
    assert a.iloc[0]["risk_score"] == b.iloc[0]["risk_score"]


def test_config_override_recomputes_escalation():
    """Lowering the escalation threshold must flip escalate flags (Req 3.5)."""
    row = _row(management_overrides=1, source_of_funds_verified="No")  # score 25
    strict = score_report(pd.DataFrame([row]), RiskConfig(escalate_at=60))
    loose = score_report(pd.DataFrame([row]), RiskConfig(escalate_at=20))
    assert strict.iloc[0]["escalate_to_finma"] == "No"
    assert loose.iloc[0]["escalate_to_finma"] == "Yes"


def test_recomputed_matches_dataset_under_defaults():
    """Sanity check: default config reproduces the dataset's risk_score (Req 3.1)."""
    ds = load_all()
    scored = score_report(ds.pep_quarterly_report, RiskConfig())
    original = pd.to_numeric(ds.pep_quarterly_report["risk_score"], errors="coerce")
    assert (scored["risk_score"] == original.astype(int)).all()
    assert (scored["risk_level"] == ds.pep_quarterly_report["risk_level"]).all()
