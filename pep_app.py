"""FINMA PEP Supervisory Analytics — Streamlit entry point.

Run with:  streamlit run pep_app.py

This app is independent of the existing app.py / reconcile.py (which operate on
dataset/). It reads only from dataset2/ (Requirement 10).

Shared helpers here are imported by the pages in pages/.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pep_analytics import db as DBM
from pep_analytics.batch import (
    convert_csv_row_to_unified,
    generate_sample_batch_csv,
    generate_sample_batch_json
)
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
from pep_analytics.ui import get_scored, sidebar_config

DBM.init_db()

BATCH_ICON_PATH = Path(__file__).resolve().parent / "assets" / "batch-upload.svg"


def _batch_icon_data_uri() -> str:
    """Return the replaceable batch-action asset as an embeddable image."""
    encoded = base64.b64encode(BATCH_ICON_PATH.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"

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
    border-bottom: 3px solid #d1d5db;
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
    background-color: #e5e7eb !important;
}

/* Active (clicked) tab: neutral grey */
[data-testid="stHeader"] a[aria-current="page"],
[data-testid="stHeader"] a[data-testid="stTopNavLink"][aria-current="page"],
[data-testid="stHeader"] a[aria-current="page"] * {
    background-color: #e5e7eb !important;   /* light grey */
    color: #1f2937 !important;              /* dark slate text */
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


@st.dialog("Batch Data Generator & Upload", width="large")
def batch_data_dialog(cfg):
    """Render batch generation and ingestion without crowding the Home page."""
    st.caption(
        "Download a complete generated dataset or upload quarterly report in CSV/JSON format.  \n"
        "The uploaded batch will be ingested into the database and trigger any necessary escalations.  \n"
        "Accepted CSV layouts: the generated unified template or the project's native "
        "`pep_quarterly_report.csv`."
    )

    download_csv, download_json = st.columns(2)
    download_csv.download_button(
        "Download Generated CSV",
        data=generate_sample_batch_csv().encode("utf-8"),
        file_name="sample_pep_batch.csv",
        mime="text/csv",
        width="stretch",
    )
    download_json.download_button(
        "Download Generated JSON",
        data=generate_sample_batch_json().encode("utf-8"),
        file_name="sample_pep_batch.json",
        mime="application/json",
        width="stretch",
    )

    uploaded_file = st.file_uploader(
        "Upload complete batch (.csv or .json)",
        type=["csv", "json"],
        key="home_batch_upload",
    )
    if uploaded_file is None:
        return

    batch_records = []
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            uploaded = pd.read_csv(uploaded_file)
            native_quarterly = "volume_vs_expected" in uploaded.columns
            batch_records = [
                convert_csv_row_to_unified(row, cfg)
                for _, row in uploaded.iterrows()
            ]
            st.info(
                f"Loaded **{'native quarterly-report' if native_quarterly else 'unified'}** "
                f"CSV with **{len(uploaded)}** rows and "
                f"**{len(uploaded.columns)}** columns."
            )
        else:
            payload = json.load(uploaded_file)
            if isinstance(payload, list):
                batch_records = payload
            elif isinstance(payload, dict):
                batch_records = [payload]
            else:
                raise ValueError("JSON must contain one record object or a list of records.")
            st.info(f"Loaded JSON with **{len(batch_records)}** unified records.")
    except Exception as exc:
        st.error(f"Could not parse the uploaded batch: {exc}")
        return

    if not batch_records:
        st.warning("The uploaded file contains no records.")
        return

    preview_rows = []
    escalation_count = 0
    for record in batch_records:
        entity = record.get("entity", {})
        report = record.get("report", {})
        escalated = (
            report.get("escalate_to_finma") == "Yes"
            or float(report.get("risk_score") or 0) >= 60
        )
        escalation_count += int(escalated)
        preview_rows.append({
            "Entity ID": entity.get("entity_id", "Unknown"),
            "Name": entity.get("name", "Unknown"),
            "Bank": entity.get("swiss_bank", "Unknown"),
            "Quarter": report.get("quarter", "Unknown"),
            "Risk Score": float(report.get("risk_score") or 0),
            "Status": "Escalation" if escalated else "Standard intake",
        })

    total = len(batch_records)
    p1, p2, p3 = st.columns(3)
    p1.metric("Batch Records", total)
    p2.metric("Escalations", escalation_count)
    p3.metric("Standard", total - escalation_count)
    st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    if st.button(
        f"Commit Entire Batch ({total} records)",
        type="primary",
        width="stretch",
        key="home_batch_commit",
    ):
        with st.spinner("Applying complete batch update..."):
            result = DBM.batch_insert_unified_records(
                batch_records,
                event_type="BATCH_FILE_INGESTION",
            )
            st.cache_data.clear()
        st.success(
            f"Batch update complete: {result['total_ingested']} records ingested; "
            f"{result['escalations_triggered']} escalations registered."
        )


@st.dialog("Reset entire database", dismissible=False)
def reset_database_dialog():
    """Confirm and execute a destructive database rebuild."""
    st.error(
        "This deletes all uploaded records, cases, officer assignments, audit logs, "
        "and other database changes. The schema will be recreated and baseline CSV "
        "data plus the default officer directory will be seeded again."
    )
    confirmed = st.checkbox(
        "I understand that all current database changes will be deleted.",
        key="confirm_full_database_reset",
    )
    cancel_col, reset_col = st.columns(2)
    if cancel_col.button("Cancel", width="stretch", key="cancel_full_database_reset"):
        st.rerun()
    if reset_col.button(
        "Reset database",
        type="primary",
        icon=":material/delete_forever:",
        width="stretch",
        disabled=not confirmed,
        key="confirm_full_database_reset_button",
    ):
        with st.spinner("Dropping tables, rebuilding schema, and reseeding baseline data..."):
            DBM.reset_db_to_baseline()
            st.cache_data.clear()
            st.session_state.clear()
            st.session_state["database_reset_complete"] = True
        st.rerun()


# ---- landing page ----
def home_page():
    cfg = sidebar_config()
    title_col, action_col = st.columns([8, 1], vertical_alignment="center")
    title_col.title("FINMA PEP Supervisory Analytics")
    st.markdown(
        """
        <style>
        .st-key-open_batch_dialog button,
        .st-key-open_database_reset_dialog button {
            width: 2.5rem !important;
            height: 2.5rem !important;
            min-height: 2.5rem !important;
            padding: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with action_col.container(horizontal=True, horizontal_alignment="right"):
        if st.button(
            "",
            type="primary",
            icon=":material/upload:",
            width="content",
            help="Upload a batch file, or download generated sample CSV/JSON files.",
            key="open_batch_dialog",
        ):
            batch_data_dialog(cfg)
        if st.button(
            "",
            icon=":material/restart_alt:",
            width="content",
            help="Delete all database changes, rebuild the schema, and reseed baseline data.",
            key="open_database_reset_dialog",
        ):
            reset_database_dialog()
    st.caption("Regulator-side analytics over bank-submitted PEP data.")

    if st.session_state.pop("database_reset_complete", False):
        st.success("Database reset complete. Schema and baseline data were rebuilt.")

    ds, scored = get_scored(cfg)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PEP client-quarters", f"{len(scored):,}")
    c2.metric("Distinct PEP-linked entities", f"{scored['entity_id'].nunique():,}")
    c3.metric("High-risk client-quarters", int((scored["risk_level"] == "High").sum()))
    c4.metric("Escalations", int((scored["escalate_to_finma"] == "Yes").sum()))

    st.subheader("Explore the dashboard")

    pages = [
        ("Overview", "pages/1_Overview.py", "Portfolio KPIs and risk by bank"),
        ("Watchlist", "pages/2_Watchlist.py", "High-risk client-quarters with score breakdown"),
        ("Network", "pages/3_Network.py", "PEP network graph and cluster analytics"),
        ("Governance", "pages/4_Governance.py", "Source-of-funds gaps, overrides, introducer reliance"),
        ("Drilldown", "pages/6_Drilldown.py", "One entity: transactions, counterparties, subgraph, risk history"),
        ("Case Management", "pages/8_Case_Management.py", "Manage cases, assign officers, and track resolution"),
    ]

    for row_start in range(0, len(pages), 3):
        cols = st.columns(3, gap="medium")
        for col, (title, path, desc) in zip(cols, pages[row_start:row_start + 3]):
            with col.container(border=True):
                st.markdown(
                    f'<div style="display:flex;align-items:center;">'
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
    st.Page("pages/8_Case_Management.py", title="Case Management"),
], position="top")

navigation.run()
