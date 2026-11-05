"""Shared Streamlit UI helpers used by the entry point and application pages."""
from __future__ import annotations

import streamlit as st

from pep_analytics import db as DBM
from pep_analytics.config import RiskConfig
from pep_analytics.data_loader import DataValidationError, load_all
from pep_analytics.scoring import score_report


@st.cache_data(show_spinner="Loading dataset2…")
def _load():
    return load_all()


def get_data():
    """Load datasets, surfacing validation errors in the UI."""
    try:
        return _load()
    except DataValidationError as exc:
        st.error(f"Data validation error: {exc}")
        st.stop()


def sidebar_config() -> RiskConfig:
    """Render the shared adjustable-threshold sidebar."""
    st.sidebar.header("Risk model configuration")
    base = RiskConfig()
    escalate_at = st.sidebar.slider(
        "Escalation threshold (risk score)", 0, 100, base.escalate_at, 5,
        help="Client-quarters at or above this score escalate to FINMA.",
    )
    high_at = st.sidebar.slider("High-risk band starts at", 0, 100, base.high_at, 5)
    medium_at = st.sidebar.slider("Medium-risk band starts at", 0, high_at, base.medium_at, 5)
    max_days = st.sidebar.number_input(
        "Max SAR delay before escalation (days)", 0, 3650, base.max_days_alert_to_sar, 5,
    )
    sof_min = st.sidebar.number_input(
        "Source-of-funds materiality (USD inflow)", 0, 10_000_000,
        int(base.sof_materiality_min), 10_000,
    )
    interval = st.sidebar.number_input(
        "KYC review interval (quarters)", 1, 40, base.kyc_review_interval_quarters,
    )
    st.sidebar.divider()
    st.sidebar.subheader("Live Database")
    counts = DBM.get_counts()
    st.sidebar.caption(
        f"Entities: {counts.get('entities', 0):,} | "
        f"Reports: {counts.get('pep_quarterly_report', 0):,}"
    )
    if st.sidebar.button("🔄 Reset to Baseline", key="sidebar_reset_btn"):
        DBM.reset_db_to_baseline()
        st.cache_data.clear()
        st.sidebar.success("Database reset to baseline!")
        st.rerun()

    try:
        return base.with_overrides(
            escalate_at=int(escalate_at),
            high_at=int(high_at),
            medium_at=int(medium_at),
            max_days_alert_to_sar=int(max_days),
            sof_materiality_min=float(sof_min),
            kyc_review_interval_quarters=int(interval),
        )
    except ValueError as exc:
        st.sidebar.error(str(exc))
        return base


def get_scored(cfg: RiskConfig):
    """Return datasets and the quarterly report scored with ``cfg``."""
    ds = get_data()
    return ds, score_report(ds.pep_quarterly_report, cfg)
