"""Live CMS Gateway & Streaming Simulator for FINMA PEP Supervision.

Allows single-entry case ingestion (CMS portal) with scenario-aware presets
mirroring the HSBC Lebanon / Forry case, and provides an interval-based
live streaming simulator that pushes events into SQLite with instant
supervisory escalation alerting.
"""
from __future__ import annotations

import random
import time

import pandas as pd
import streamlit as st

from pep_analytics import db as DBM
from pep_analytics import generator as GEN
from pep_analytics.config import RiskConfig
from pep_analytics.scoring import score_report
from pep_app import sidebar_config

st.set_page_config(page_title="Live CMS Gateway — FINMA PEP Supervision", layout="wide")

st.title("Live CMS Gateway & Stream Simulator")
st.caption(
    "Mock live database ingestion for supervisory analytics. Enter individual "
    "cases via the CMS portal, pre-fill realistic Lebanon/Forry typologies "
    "(not placeholder text), or simulate live interval event streams into SQLite."
)

cfg = sidebar_config()

# ---- Database Management in Sidebar ----
st.sidebar.divider()
st.sidebar.subheader("Live Database Status")
counts = DBM.get_counts()
st.sidebar.markdown(
    f"""
- **Entities:** {counts.get('entities', 0):,}
- **Quarterly Reports:** {counts.get('pep_quarterly_report', 0):,}
- **Network Edges:** {counts.get('network_edges', 0):,}
- **Audit Events:** {counts.get('stream_audit_log', 0):,}
"""
)

if st.sidebar.button("🔄 Reset Database to Baseline", type="secondary"):
    with st.spinner("Restoring dataset2 baseline..."):
        DBM.reset_db_to_baseline()
        st.cache_data.clear()
        st.sidebar.success("Database restored to baseline!")
        st.rerun()

# ---- Tabs ----
tab_cms, tab_stream, tab_audit = st.tabs(
    ["CMS Single-Entry Portal", "Live Stream Simulator", "Audit Trail & DB Health"]
)

# ==============================================================================
# TAB 1: CMS Single-Entry Portal
# ==============================================================================
with tab_cms:
    st.subheader("Supervisory Case Management System (CMS) Entry")
    st.markdown(
        "Submit a new PEP client profile, associated network relationship, and "
        "quarterly compliance report. Use **Scenario-Aware Presets** to populate "
        "realistic data derived from the HSBC Lebanon / Forry investigation."
    )

    # Preset selector & auto-fill button
    p_col1, p_col2 = st.columns([3, 1])
    preset_choice = p_col1.selectbox(
        "Select Scenario-Aware Typology Preset",
        options=list(GEN.PRESET_NAMES.keys()),
        format_func=lambda k: GEN.PRESET_NAMES[k],
    )

    # Maintain session state for form pre-filling
    if "form_preset_data" not in st.session_state:
        st.session_state["form_preset_data"] = GEN.generate_unified_record(
            preset_choice, quarter="2016Q4", cfg=cfg
        )

    if p_col2.button("✨ Pre-fill Form with Preset", use_container_width=True):
        st.session_state["form_preset_data"] = GEN.generate_unified_record(
            preset_choice, quarter="2016Q4", cfg=cfg
        )
        st.toast(f"Form populated with realistic {preset_choice} profile!")
        st.rerun()

    cur_data = st.session_state["form_preset_data"]
    ent = cur_data["entity"]
    edg = cur_data["edge"]
    rep = cur_data["report"]

    with st.form("cms_single_entry_form"):
        st.markdown("#### 1. Entity KYC Profile")
        e1, e2, e3 = st.columns(3)
        form_ent_id = e1.text_input("Entity ID", value=ent["entity_id"])
        form_name = e2.text_input("Entity Name", value=ent["name"])
        form_type = e3.selectbox(
            "Entity Type",
            ["Company", "Person", "Government body"],
            index=["Company", "Person", "Government body"].index(ent["entity_type"]),
        )

        e4, e5, e6 = st.columns(3)
        form_country = e4.text_input("Country (ISO)", value=ent["country"])
        pep_cats = ["PEP", "PEP family", "PEP close associate", "PEP-owned company", "Not PEP"]
        form_pep_cat = e5.selectbox(
            "PEP Category",
            pep_cats,
            index=pep_cats.index(ent["pep_category"]) if ent["pep_category"] in pep_cats else 0,
        )
        form_bank = e6.selectbox(
            "Swiss Booking Bank",
            ["CH_A", "CH_B", "CH_C", "CH_D", "None (foreign counterparty)"],
            index=["CH_A", "CH_B", "CH_C", "CH_D", "None (foreign counterparty)"].index(ent["swiss_bank"])
            if ent["swiss_bank"] in ["CH_A", "CH_B", "CH_C", "CH_D"] else 0,
        )

        e7, e8, e9, e10 = st.columns(4)
        form_offshore = e7.selectbox("Offshore Jurisdiction", ["Yes", "No"], index=0 if ent["offshore_jurisdiction"] == "Yes" else 1)
        form_flagged_bank = e8.selectbox("Flagged as PEP by Bank", ["Yes", "No"], index=0 if ent["flagged_as_pep_by_bank"] == "Yes" else 1)
        form_sof_ver = e9.selectbox("Source of Funds Verified", ["Yes", "No", "Unknown"], index=0 if ent["source_of_funds_verified"] == "Yes" else 1)
        form_linked_pep = e10.text_input("Linked PEP Name", value=ent["linked_pep_name"] or "")

        st.divider()
        st.markdown("#### 2. Network Relationship (Edge)")
        d1, d2, d3 = st.columns(3)
        form_edge_target = d1.text_input("Target Entity ID / Name", value=edg["target_name"])
        form_edge_type = d2.selectbox(
            "Relationship Type",
            ["Nominee director", "Owns", "Family", "Close associate", "Money transfer", "Director", "Employed by"],
            index=["Nominee director", "Owns", "Family", "Close associate", "Money transfer", "Director", "Employed by"].index(edg["edge_type"])
            if edg["edge_type"] in ["Nominee director", "Owns", "Family", "Close associate", "Money transfer", "Director", "Employed by"] else 0,
        )
        form_known_bank = d3.selectbox(
            "Relationship Known to Bank?",
            ["Yes", "No"],
            index=0 if edg["known_to_bank"] == "Yes" else 1,
            help="'No' renders as a dashed red link in network graph (found by regulator/independent review).",
        )

        st.divider()
        st.markdown("#### 3. Mandated Quarterly Compliance Submission")
        q1, q2, q3, q4 = st.columns(4)
        form_quarter = q1.text_input("Reporting Quarter", value=rep["quarter"])
        form_inflow = q2.number_input("Quarterly Inflow (USD)", value=float(rep["inflow_usd"]), min_value=0.0, step=10_000.0)
        form_outflow = q3.number_input("Quarterly Outflow (USD)", value=float(rep["outflow_usd"]), min_value=0.0, step=10_000.0)
        form_cash = q4.number_input("Cash Deposits (USD)", value=float(rep["cash_usd"]), min_value=0.0, step=5_000.0)

        q5, q6, q7, q8 = st.columns(4)
        calc_ratio = form_outflow / form_inflow if form_inflow > 0 else 0.0
        form_ratio = q5.number_input("Pass-Through Ratio", value=float(round(calc_ratio, 3)), min_value=0.0, max_value=5.0, step=0.01)
        form_vol_exp = q6.number_input("Volume vs Expected Ratio", value=float(rep["volume_vs_expected"]), min_value=0.0, step=0.5)
        form_dest_share = q7.number_input("High-Risk Destination Share", value=float(rep["high_risk_destination_share"]), min_value=0.0, max_value=1.0, step=0.05)
        form_days_sar = q8.number_input("Days Alert → SAR", value=int(rep["days_alert_to_sar"]), min_value=0, step=5)

        q9, q10, q11 = st.columns(3)
        form_overrides = q9.number_input("Management Overrides Count", value=int(rep["management_overrides"]), min_value=0, step=1)
        form_exit_rec = q10.selectbox("Compliance Recommended Exit/SAR?", ["Yes (1)", "No (0)"], index=0 if rep["compliance_recommended_exit_or_sar"] == 1 else 1)
        form_intro_used = q11.selectbox("Introducer Assurance Relied Upon?", ["Yes (1)", "No (0)"], index=0 if rep["introducer_assurance_used"] == 1 else 1)

        submitted = st.form_submit_button("🚀 Submit Unified Record to Live Database", type="primary", use_container_width=True)

        if submitted:
            # Build unified payloads
            new_entity = {
                "entity_id": form_ent_id.strip(),
                "name": form_name.strip(),
                "entity_type": form_type,
                "country": form_country.strip(),
                "pep_category": form_pep_cat,
                "linked_pep_id": ent.get("linked_pep_id"),
                "linked_pep_name": form_linked_pep.strip() or None,
                "pep_role": ent.get("pep_role"),
                "flagged_as_pep_by_bank": form_flagged_bank,
                "swiss_bank": form_bank,
                "offshore_jurisdiction": form_offshore,
                "declared_income_usd": ent.get("declared_income_usd", 200_000.0),
                "expected_monthly_volume_usd": ent.get("expected_monthly_volume_usd", 50_000.0),
                "source_of_funds_verified": form_sof_ver,
                "bank_risk_rating": ent.get("bank_risk_rating", "Medium"),
                "is_suspicious": ent.get("is_suspicious", "No"),
                "scenario": ent.get("scenario", "CMS_CUSTOM"),
            }

            new_edge = {
                "source_id": form_ent_id.strip(),
                "source_name": form_name.strip(),
                "target_id": edg.get("target_id", "TARGET-01"),
                "target_name": form_edge_target.strip(),
                "edge_type": form_edge_type,
                "detail": edg.get("detail", "CMS Submission link"),
                "total_usd": form_inflow,
                "txn_count": 1,
                "known_to_bank": form_known_bank,
                "found_via": "CMS Portal",
                "is_suspicious": ent.get("is_suspicious", "No"),
            }

            raw_rep = {
                "quarter": form_quarter.strip(),
                "entity_id": form_ent_id.strip(),
                "name": form_name.strip(),
                "pep_category": form_pep_cat,
                "linked_pep_name": form_linked_pep.strip() or None,
                "swiss_bank": form_bank,
                "flagged_as_pep_by_bank": form_flagged_bank,
                "inflow_usd": form_inflow,
                "outflow_usd": form_outflow,
                "cash_usd": form_cash,
                "pass_through_ratio": form_ratio,
                "volume_vs_expected": form_vol_exp,
                "high_risk_destination_share": form_dest_share,
                "n_counterparties": 3,
                "alerts_raised": 1 if form_days_sar > 0 else 0,
                "compliance_recommended_exit_or_sar": 1 if "Yes" in form_exit_rec else 0,
                "management_overrides": int(form_overrides),
                "introducer_assurance_used": 1 if "Yes" in form_intro_used else 0,
                "sar_filed": 1 if form_days_sar > 0 else 0,
                "days_alert_to_sar": int(form_days_sar),
                "source_of_funds_verified": form_sof_ver,
                "is_suspicious": ent.get("is_suspicious", "No"),
                "scenario": ent.get("scenario", "CMS_CUSTOM"),
            }

            # Derive supervisory risk score
            scored_df = score_report(pd.DataFrame([raw_rep]), cfg)
            row_score = scored_df.iloc[0]
            raw_rep["risk_score"] = int(row_score["risk_score"])
            raw_rep["risk_level"] = str(row_score["risk_level"])
            raw_rep["escalate_to_finma"] = str(row_score["escalate_to_finma"])

            # Commit to SQLite
            DBM.insert_unified_pep_record(
                entity=new_entity,
                edge=new_edge,
                report=raw_rep,
                transactions=cur_data.get("transactions"),
                event_type="CMS_MANUAL_ENTRY",
            )
            st.cache_data.clear()

            # Display Escalation / Risk Alert Banner
            score_val = raw_rep["risk_score"]
            if raw_rep["escalate_to_finma"] == "Yes":
                st.error(
                    f"🚨 **FINMA ESCALATION MANDATED (Risk Score: {score_val}/100 — Level: High)**\n\n"
                    f"Entity **{form_name}** ({form_ent_id}) has breached regulatory thresholds.\n\n"
                    f"Contributing factors: {', '.join([f'{f} (+{p})' for f, p in row_score.get('score_factors', [])])}"
                )
            else:
                st.success(
                    f"✅ Record successfully ingested into live database!\n\n"
                    f"Risk Score: **{score_val}/100** ({raw_rep['risk_level']}). No escalation required."
                )

# ==============================================================================
# TAB 2: Live Stream Simulator
# ==============================================================================
with tab_stream:
    st.subheader("Interval-Based Live Stream Simulator")
    st.markdown(
        "Simulate an active stream of incoming banking submissions. The simulator "
        "generates cohesive lifecycle records and pushes them into SQLite, updating "
        "real-time risk rankings and the supervisory network."
    )

    s_col1, s_col2, s_col3 = st.columns(3)
    stream_preset = s_col1.selectbox(
        "Typology Stream Generator",
        options=["MIXED_TYPOLOGIES"] + list(GEN.PRESET_NAMES.keys()),
        format_func=lambda k: "🎲 Mixed Typologies (Lebanon Investigation Stream)" if k == "MIXED_TYPOLOGIES" else GEN.PRESET_NAMES[k],
    )
    stream_quarter = s_col2.selectbox(
        "Target Quarter",
        ["2016Q4", "2017Q1", "2017Q2", "2017Q3", "2017Q4"],
        index=0,
    )
    stream_count = s_col3.slider("Number of Events to Stream", min_value=1, max_value=10, value=3)

    ctrl_col1, ctrl_col2 = st.columns(2)
    step_clicked = ctrl_col1.button("▶️ Step 1 Event (Single Pulse)", type="secondary", use_container_width=True)
    batch_clicked = ctrl_col2.button(f"⚡ Stream {stream_count} Events Now", type="primary", use_container_width=True)

    if step_clicked or batch_clicked:
        count = 1 if step_clicked else stream_count
        progress_bar = st.progress(0, text="Streaming simulated live events...")
        escalation_alerts = []

        for i in range(count):
            typology = (
                random.choice(["COMMISSION_DIVERSION", "PROCUREMENT_KICKBACK", "FAMILY_STRUCTURING", "CLEAN_PEP_CONTROL"])
                if stream_preset == "MIXED_TYPOLOGIES"
                else stream_preset
            )
            rec = GEN.generate_unified_record(typology, quarter=stream_quarter, cfg=cfg)

            DBM.insert_unified_pep_record(
                entity=rec["entity"],
                edge=rec["edge"],
                report=rec["report"],
                transactions=rec["transactions"],
                event_type="STREAM_EVENT",
            )

            if rec["report"]["escalate_to_finma"] == "Yes":
                escalation_alerts.append(
                    f"**{rec['entity']['name']}** ({rec['entity']['entity_id']}) — Score {rec['report']['risk_score']}/100 — {typology}"
                )

            progress_bar.progress((i + 1) / count, text=f"Ingested event {i + 1} of {count}...")
            time.sleep(0.3)  # Brief visual interval pulse

        st.cache_data.clear()
        progress_bar.empty()
        st.success(f"Successfully streamed {count} event(s) into the live database!")

        if escalation_alerts:
            st.error(
                f"⚠️ **{len(escalation_alerts)} FINMA ESCALATION(S) TRIGGERED IN THIS STREAM BATCH:**\n\n"
                + "\n\n".join(f"- {a}" for a in escalation_alerts)
            )

    # Real-Time Event Audit Ticker
    st.divider()
    st.subheader("Live Event Ticker (Recent Ingestions)")
    audit_df = DBM.get_audit_log(limit=15)
    if audit_df.empty:
        st.info("No live stream events recorded yet.")
    else:
        for _, log_row in audit_df.iterrows():
            is_esc = log_row["escalate_to_finma"] == "Yes"
            icon = "🚨" if is_esc else "ℹ️"
            badge = "🔴 ESCALATED TO FINMA" if is_esc else f"🟢 Score: {log_row['risk_score']:.0f}"
            with st.container():
                c_a, c_b, c_c = st.columns([1, 3, 2])
                c_a.markdown(f"**{log_row['timestamp']}**")
                c_b.markdown(f"{icon} **{log_row['entity_name']}** ({log_row['entity_id']}) — *{log_row['event_type']}*")
                c_c.markdown(f"{badge} | Bank: **{log_row['swiss_bank']}**")
                st.caption(f"Details: {log_row['details']}")
                st.divider()

# ==============================================================================
# TAB 3: Audit Trail & DB Health
# ==============================================================================
with tab_audit:
    st.subheader("Supervisory Audit Trail & Database Health")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Entities", f"{counts.get('entities', 0):,}")
    c2.metric("Quarterly Reports", f"{counts.get('pep_quarterly_report', 0):,}")
    c3.metric("Network Edges", f"{counts.get('network_edges', 0):,}")
    c4.metric("Stream Audit Log Rows", f"{counts.get('stream_audit_log', 0):,}")

    st.subheader("Complete Live Audit Log")
    full_audit = DBM.get_audit_log(limit=100)
    st.dataframe(full_audit, use_container_width=True, hide_index=True)

    if not full_audit.empty:
        st.download_button(
            "📥 Download Audit Trail (CSV)",
            data=full_audit.to_csv(index=False).encode("utf-8"),
            file_name="stream_audit_trail.csv",
            mime="text/csv",
        )
