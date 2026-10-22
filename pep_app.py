"""FINMA PEP Supervisory Analytics — Streamlit entry point.

Run with:  streamlit run pep_app.py

This app is independent of the existing app.py / reconcile.py (which operate on
dataset/). It reads only from dataset2/ (Requirement 10).

Shared helpers here are imported by the pages in pages/.
"""
from __future__ import annotations

import streamlit as st

from pep_analytics import db as DBM
from pep_analytics.config import RiskConfig
from pep_analytics.data_loader import DataValidationError, load_all
from pep_analytics.scoring import score_report

st.set_page_config(page_title="FINMA PEP Supervisory Analytics", layout="wide")


@st.cache_data(show_spinner="Loading dataset2…")
def _load():
    ds = load_all()
    return ds


def get_data():
    """Load datasets, surfacing validation errors in the UI (Requirement 2.3)."""
    try:
        return _load()
    except DataValidationError as exc:
        st.error(f"Data validation error: {exc}")
        st.stop()


def sidebar_config() -> RiskConfig:
    """Render the adjustable-threshold sidebar and return an overridden config.

    Shared across pages so a change recomputes every page consistently
    (Requirements 3.4, 3.5).
    """
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
        f"Entities: {counts.get('entities', 0):,} | Reports: {counts.get('pep_quarterly_report', 0):,}"
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
    """Datasets + the scored quarterly report for the current config."""
    ds = get_data()
    scored = score_report(ds.pep_quarterly_report, cfg)
    return ds, scored


# ---- landing page ----
st.title("FINMA PEP Supervisory Analytics")
st.caption(
    "Regulator-side analytics over bank-submitted PEP data. Risk is re-derived "
    "independently of the bank's own alerts; answer-key columns are used only on "
    "the Validation page."
)

cfg = sidebar_config()
ds, scored = get_scored(cfg)

c1, c2, c3, c4 = st.columns(4)
c1.metric("PEP client-quarters", f"{len(scored):,}")
c2.metric("Distinct PEP-linked entities", f"{scored['entity_id'].nunique():,}")
c3.metric("High-risk client-quarters", int((scored["risk_level"] == "High").sum()))
c4.metric("Escalations", int((scored["escalate_to_finma"] == "Yes").sum()))

st.markdown(
    """
Use the pages in the sidebar:

1. **Overview** — portfolio KPIs and risk by bank
2. **Watchlist** — high-risk client-quarters with score breakdown
3. **Network** — PEP network graph + cluster analytics (hidden links highlighted)
4. **Governance** — source-of-funds gaps, overrides, introducer reliance
5. **Review** — independent KYC-review worklist
6. **Drilldown** — one entity: transactions, counterparties, subgraph, risk history
7. **Validation** — detection quality vs the answer key
8. **Live CMS** — manual case submission, Lebanon typology presets & interval stream simulator
"""
)
