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
    generate_sample_batch_json,
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
    </style>
    """,
    unsafe_allow_html=True,
)


@st.dialog("Batch Data Generator & Upload", width="large")
def batch_data_dialog(cfg):
    """Render batch generation and ingestion without crowding the Home page."""
    st.caption(
        "Download a complete generated dataset or upload quarterly report in CSV/JSON format.  \n"
        "The uploaded batch will be ingested into the database and trigger any necessary escalations."
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
            batch_records = [
                convert_csv_row_to_unified(row, cfg)
                for _, row in uploaded.iterrows()
            ]
            st.info(
                f"Loaded CSV with **{len(uploaded)}** rows and "
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


# ---- landing page ----
def home_page():
    cfg = sidebar_config()
    title_col, action_col = st.columns([9, 1], vertical_alignment="center")
    title_col.title("FINMA PEP Supervisory Analytics")
    st.markdown(
        f"""
        <style>
        .st-key-open_batch_dialog button {{
            width: 2.5rem;
            height: 2.5rem;
            margin-left: auto;
            border: 1px solid var(--secondary-background-color);
            border-radius: 0.5rem;
            background-color: var(--secondary-background-color);
            background-image: url("{_batch_icon_data_uri()}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: 1.35rem 1.35rem;
            transition: transform 120ms ease, border-color 120ms ease;
        }}
        .st-key-open_batch_dialog button:hover {{
            transform: translateY(-1px);
            border-color: #ff4b4b;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if action_col.button(
        "",
        help=(
            "Generate sample CSV/JSON files or upload and commit a complete "
            "batch without event streaming."
        ),
        key="open_batch_dialog",
    ):
        batch_data_dialog(cfg)
    st.caption("Regulator-side analytics over bank-submitted PEP data.")

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
    5. **Drilldown** — one entity: transactions, counterparties, subgraph, risk history
    6. **Case Management** — case monitoring and officer assignments
    
    """
    )



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
