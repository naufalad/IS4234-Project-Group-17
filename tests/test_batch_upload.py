"""Regression tests for supported CSV batch layouts."""
from __future__ import annotations

import math

import pandas as pd

from pep_analytics.batch import convert_csv_row_to_unified
from pep_analytics.config import RiskConfig


def test_native_quarterly_row_accepts_nan_fields():
    row = pd.Series({
        "quarter": "2026Q1",
        "entity_id": "E-TEST",
        "name": "Test Entity",
        "pep_category": "PEP",
        "linked_pep_name": math.nan,
        "swiss_bank": "CH_A",
        "flagged_as_pep_by_bank": "Yes",
        "inflow_usd": 100_000,
        "outflow_usd": 80_000,
        "cash_usd": 0,
        "pass_through_ratio": math.nan,
        "volume_vs_expected": 1.0,
        "high_risk_destination_share": 0.0,
        "n_counterparties": 2,
        "alerts_raised": 0,
        "compliance_recommended_exit_or_sar": 0,
        "management_overrides": 0,
        "introducer_assurance_used": 0,
        "sar_filed": 0,
        "days_alert_to_sar": math.nan,
        "source_of_funds_verified": "Yes",
        "is_suspicious": "No",
        "scenario": "TEST",
    })

    record = convert_csv_row_to_unified(row, RiskConfig())

    assert record["edge"] is None
    assert record["entity"]["linked_pep_name"] is None
    assert record["report"]["days_alert_to_sar"] == 0
    assert record["report"]["pass_through_ratio"] == 0.8
