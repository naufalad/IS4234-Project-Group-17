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

import plotly.io as pio
import plotly.graph_objects as go

pio.templates["pep"] = go.layout.Template(
    layout=dict(
        title=dict(font=dict(size=16), x=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, l=0, r=0, b=0),
        xaxis=dict(gridcolor="#e5e7eb"),
        yaxis=dict(gridcolor="#e5e7eb"),
    )
)
pio.templates.default = "plotly+pep"

st.set_page_config(page_title="FINMA PEP Supervisory Analytics", layout="wide", initial_sidebar_state="collapsed",
)

st.set_page_config(page_title="FINMA PEP Supervisory Analytics", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .stApp h1 {
        font-size: 2.4rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
        padding-bottom: 0.4rem !important;
        margin-bottom: 0.6rem;
        border-bottom: 4px solid #FF4B4B;
        display: inline-block;
    }
    .stApp h2 {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em;
        padding-left: 0.75rem !important;
        border-left: 5px solid #FF4B4B;
        margin-top: 1.5rem;
    }
    .stApp h3 {
        font-size: 1.25rem !important;
        font-weight: 600 !important;
        color: #4a4f5c;
    }
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] p {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #6b7280 !important;
    }
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] div {
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        color: #FF4B4B !important;
        line-height: 1.1 !important;
    }
    .stApp hr {
        border-color: #e5e7eb !important;
        margin: 1.5rem 0 !important;
    }

    /* Full-width top bar */
[data-testid="stHeader"] {
    background-color: #ffffff !important;
    border-bottom: 3px solid #FF4B4B;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    width: 100% !important;
    padding: 0.25rem 1rem !important;
}

/* Nav links */
[data-testid="stHeader"] a {
    font-weight: 600 !important;
    border-radius: 6px !important;
    padding: 0.4rem 1rem !important;
    transition: background-color 0.15s ease;
}
[data-testid="stHeader"] a:hover {
    background-color: #ffe5e5 !important;
}

/* Active (clicked) tab: red with white text */
[data-testid="stHeader"] a[aria-current="page"],
[data-testid="stHeader"] a[data-testid="stTopNavLink"][aria-current="page"],
[data-testid="stHeader"] a[aria-current="page"] * {
    background-color: #FF4B4B !important;
    color: #ffffff !important;
}

/* Dashboard cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(a[data-testid="stPageLink-NavLink"]) {
    border: 1px solid #e5e7eb !important;
    border-top: 4px solid #FF4B4B !important;
    border-radius: 12px !important;
    padding: 0.5rem 0.5rem !important;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
    min-height: 190px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(a[data-testid="stPageLink-NavLink"]):hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(255, 75, 75, 0.18);
}

/* Card title */
.card-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: #262730;
    margin-bottom: 0.25rem;
}
.card-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.4rem;
    height: 2.4rem;
    border-radius: 10px;
    background: #fff0f0;
    margin-right: 0.6rem;
    font-size: 1.3rem;
}

/* The "Open" link as a red pill button */
a[data-testid="stPageLink-NavLink"] {
    color: #FF4B4B !important;
    font-weight: 700 !important;
    border: 1px solid #FF4B4B;
    border-radius: 999px;
    padding: 0.25rem 0.9rem !important;
    width: fit-content;
}
a[data-testid="stPageLink-NavLink"]:hover {
    background: #FF4B4B !important;
    color: #ffffff !important;
}
a[data-testid="stPageLink-NavLink"]:hover * {
    color: #ffffff !important;
}

/* Section headers: st.header (h2) and st.subheader (h3) */
.stApp h2,
.stApp h3 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
    color: #262730 !important;
    padding: 0.15rem 0 0.15rem 0.85rem !important;
    border-left: 5px solid #FF4B4B;
    margin-top: 2rem !important;
    margin-bottom: 0.75rem !important;
    line-height: 1.3 !important;
}

/* Smaller sub-sub headers (h4) */
.stApp h4 {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    color: #4a4f5c !important;
    margin-top: 1.25rem !important;
}
    </style>
    """,
    unsafe_allow_html=True,
)


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
def home_page():
    st.title("FINMA PEP Supervisory Analytics")
    st.caption("Regulator-side analytics over bank-submitted PEP data.")

    cfg = sidebar_config()
    ds, scored = get_scored(cfg)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PEP client-quarters", f"{len(scored):,}")
    c2.metric("Distinct PEP-linked entities", f"{scored['entity_id'].nunique():,}")
    c3.metric("High-risk client-quarters", int((scored["risk_level"] == "High").sum()))
    c4.metric("Escalations", int((scored["escalate_to_finma"] == "Yes").sum()))

    st.subheader("Explore the dashboard")

    pages = [
        ("📊", "Overview", "pages/1_Overview.py", "Portfolio KPIs and risk by bank"),
        ("🚩", "Watchlist", "pages/2_Watchlist.py", "High-risk client-quarters with score breakdown"),
        ("🕸️", "Network", "pages/3_Network.py", "PEP network graph and cluster analytics"),
        ("🏛️", "Governance", "pages/4_Governance.py", "Source-of-funds gaps, overrides, introducer reliance"),
        ("🔍", "Drilldown", "pages/6_Drilldown.py", "One entity: transactions, counterparties, subgraph, risk history"),
        ("⚡", "Live CMS", "pages/8_Live_CMS.py", "Submit a case here"),
    ]

    for row_start in range(0, len(pages), 3):
        cols = st.columns(3, gap="medium")
        for col, (icon, title, path, desc) in zip(cols, pages[row_start:row_start + 3]):
            with col.container(border=True):
                st.markdown(
                    f'<div style="display:flex;align-items:center;">'
                    f'<span class="card-icon">{icon}</span>'
                    f'<span class="card-title">{title}</span></div>',
                    unsafe_allow_html=True,
                )
                st.caption(desc)
                st.page_link(path, label="Open →")


navigation = st.navigation([
    st.Page(home_page, title="Home", default=True),
    st.Page("pages/1_Overview.py", title="Overview"),
    st.Page("pages/2_Watchlist.py", title="Watchlist"),
    st.Page("pages/3_Network.py", title="Network"),
    st.Page("pages/4_Governance.py", title="Governance"),
    st.Page("pages/6_Drilldown.py", title="Drilldown"),
    st.Page("pages/8_Live_CMS.py", title="Live CMS"),
], position="top")

navigation.run()
