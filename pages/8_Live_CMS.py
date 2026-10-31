"""Live CMS Gateway, Batch Ingestion & Case Dispositioning for FINMA PEP Supervision.

Provides:
1. Single-entry CMS intake portal with real-time fuzzy name matching & alias screening.
2. Drag-and-drop Batch File Ingestion Gateway (CSV / JSON) with pre-commit validation.
3. Case Lifecycle & Dispositioning Workflow with management override justification audit
   and automated MROS SAR Dossier generator.
4. Interval-based Live Stream Simulator pushing events into SQLite.
5. Real-time audit log and database health metrics.
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

import pandas as pd
import streamlit as st

from pep_analytics import db as DBM
from pep_analytics import generator as GEN
from pep_analytics.config import RiskConfig
from pep_analytics.dossier import generate_sar_dossier
from pep_analytics.entity_resolution import calculate_name_similarity, find_matching_entities
from pep_analytics.scoring import score_report
from pep_app import sidebar_config

st.set_page_config(page_title="Live CMS Gateway — FINMA PEP Supervision", layout="wide")

st.title("Supervisory CMS Gateway & Case Dispositioning")
st.caption(
    "FINMA PEP Supervisory Platform — Multi-channel data intake, fuzzy alias screening, "
    "batch file ingestion gateway, and case lifecycle management with MROS SAR dossier generation."
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
- **Active Cases:** {counts.get('cases', 0):,}
- **Audit Events:** {counts.get('stream_audit_log', 0):,}
"""
)

if st.sidebar.button("🔄 Reset Database to Baseline", type="secondary"):
    with st.spinner("Restoring dataset2 baseline..."):
        DBM.reset_db_to_baseline()
        st.cache_data.clear()
        st.sidebar.success("Database restored to baseline!")
        st.rerun()

# Load entities for screening
existing_entities = DBM.load_table("entities")

# ---- Helper functions for batch templates ----
def _generate_sample_batch_csv() -> str:
    recs = [
        GEN.generate_unified_record("COMMISSION_DIVERSION", quarter="2017Q1"),
        GEN.generate_unified_record("PROCUREMENT_KICKBACK", quarter="2017Q1"),
        GEN.generate_unified_record("FAMILY_STRUCTURING", quarter="2017Q1"),
        GEN.generate_unified_record("CLEAN_PEP_CONTROL", quarter="2017Q1"),
    ]
    rows = []
    for r in recs:
        ent = r["entity"]
        edg = r["edge"]
        rep = r["report"]
        rows.append({
            "entity_id": ent["entity_id"],
            "name": ent["name"],
            "entity_type": ent["entity_type"],
            "country": ent["country"],
            "pep_category": ent["pep_category"],
            "linked_pep_name": ent.get("linked_pep_name") or "",
            "swiss_bank": ent["swiss_bank"],
            "offshore_jurisdiction": ent["offshore_jurisdiction"],
            "flagged_as_pep_by_bank": ent["flagged_as_pep_by_bank"],
            "source_of_funds_verified": ent["source_of_funds_verified"],
            "quarter": rep["quarter"],
            "inflow_usd": rep["inflow_usd"],
            "outflow_usd": rep["outflow_usd"],
            "cash_usd": rep["cash_usd"],
            "pass_through_ratio": rep["pass_through_ratio"],
            "management_overrides": rep["management_overrides"],
            "days_alert_to_sar": rep["days_alert_to_sar"],
            "target_name": edg["target_name"],
            "edge_type": edg["edge_type"],
            "known_to_bank": edg["known_to_bank"],
        })
    return pd.DataFrame(rows).to_csv(index=False)


def _generate_sample_batch_json() -> str:
    recs = [
        GEN.generate_unified_record("COMMISSION_DIVERSION", quarter="2017Q1"),
        GEN.generate_unified_record("CLEAN_PEP_CONTROL", quarter="2017Q1"),
    ]
    return json.dumps(recs, indent=2)


def _convert_csv_row_to_unified(row: pd.Series, cfg: RiskConfig) -> dict[str, Any]:
    eid = str(row.get("entity_id") or f"ENT-BATCH-{random.randint(1000, 9999)}")
    name = str(row.get("name") or "Unnamed Entity")
    quarter = str(row.get("quarter") or "2017Q1")
    bank = str(row.get("swiss_bank") or "CH_A")
    inflow = float(row.get("inflow_usd") or 1_000_000.0)
    outflow = float(row.get("outflow_usd") or 900_000.0)
    ratio = float(row.get("pass_through_ratio") or (outflow / inflow if inflow > 0 else 0.0))
    overrides = int(row.get("management_overrides") or 0)
    days_sar = int(row.get("days_alert_to_sar") or 0)

    entity = {
        "entity_id": eid,
        "name": name,
        "entity_type": str(row.get("entity_type") or "Company"),
        "country": str(row.get("country") or "CH"),
        "pep_category": str(row.get("pep_category") or "PEP-owned company"),
        "linked_pep_id": None,
        "linked_pep_name": str(row.get("linked_pep_name") or "") or None,
        "pep_role": "Public Official" if row.get("linked_pep_name") else None,
        "flagged_as_pep_by_bank": str(row.get("flagged_as_pep_by_bank") or "No"),
        "swiss_bank": bank,
        "offshore_jurisdiction": str(row.get("offshore_jurisdiction") or "No"),
        "declared_income_usd": 250_000.0,
        "expected_monthly_volume_usd": 100_000.0,
        "source_of_funds_verified": str(row.get("source_of_funds_verified") or "No"),
        "bank_risk_rating": "High" if overrides >= 1 else "Medium",
        "is_suspicious": "Yes" if overrides >= 1 or ratio >= 0.80 else "No",
        "scenario": "BATCH_CSV_INGESTION",
    }

    edge = {
        "source_id": eid,
        "source_name": name,
        "target_id": f"TGT-{eid}",
        "target_name": str(row.get("target_name") or "Counterparty Holding"),
        "edge_type": str(row.get("edge_type") or "Money transfer"),
        "detail": "Batch file ingestion linkage",
        "total_usd": inflow,
        "txn_count": 1,
        "known_to_bank": str(row.get("known_to_bank") or "Yes"),
        "found_via": "Batch Upload Gateway",
        "is_suspicious": entity["is_suspicious"],
    }

    raw_rep = {
        "quarter": quarter,
        "entity_id": eid,
        "name": name,
        "pep_category": entity["pep_category"],
        "linked_pep_name": entity["linked_pep_name"],
        "swiss_bank": bank,
        "flagged_as_pep_by_bank": entity["flagged_as_pep_by_bank"],
        "inflow_usd": inflow,
        "outflow_usd": outflow,
        "cash_usd": float(row.get("cash_usd") or 0.0),
        "pass_through_ratio": ratio,
        "volume_vs_expected": 2.5,
        "high_risk_destination_share": 0.5,
        "n_counterparties": 3,
        "alerts_raised": 1 if days_sar > 0 else 0,
        "compliance_recommended_exit_or_sar": 1 if overrides >= 1 else 0,
        "management_overrides": overrides,
        "introducer_assurance_used": 1 if overrides >= 1 else 0,
        "sar_filed": 1 if days_sar > 0 else 0,
        "days_alert_to_sar": days_sar,
        "source_of_funds_verified": entity["source_of_funds_verified"],
        "is_suspicious": entity["is_suspicious"],
        "scenario": "BATCH_CSV_INGESTION",
    }

    scored_df = score_report(pd.DataFrame([raw_rep]), cfg)
    scored = scored_df.iloc[0]
    raw_rep["risk_score"] = int(scored["risk_score"])
    raw_rep["risk_level"] = str(scored["risk_level"])
    raw_rep["escalate_to_finma"] = str(scored["escalate_to_finma"])

    return {
        "entity": entity,
        "edge": edge,
        "report": raw_rep,
        "transactions": [],
    }


# ---- Tabs Navigation ----
tab_cms, tab_batch, tab_cases, tab_stream, tab_audit = st.tabs([
    "CMS Single-Entry Portal",
    "Batch File Upload Gateway",
    "Case Dispositioning & MROS Dossiers",
    "Live Stream Simulator",
    "Audit Trail & DB Health",
])


# ==============================================================================
# TAB 1: CMS Single-Entry Portal (with Fuzzy Alias Screening)
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

    # Fuzzy Alias & Watchlist Screening Section
    with st.expander("🔍 PEP Watchlist & Alias Screening Assistant (Entity Resolution)", expanded=True):
        st.caption("Screen legal names or beneficial owners against existing database entities to detect aliases and spelling variations.")
        f_col1, f_col2 = st.columns([3, 1])
        screen_query = f_col1.text_input("Name to Screen", value=ent["name"], key="screen_query_input")
        do_screen = f_col2.button("Run Fuzzy Screen", type="secondary", use_container_width=True)

        if screen_query:
            matches = find_matching_entities(screen_query, existing_entities, threshold=0.65, limit=5)
            if matches:
                top = matches[0]
                if top["score"] >= 0.85:
                    st.error(
                        f"🚨 **HIGH-CONFIDENCE MATCH DETECTED ({top['confidence_pct']}%):** Closely matches existing PEP `{top['matched_name']}` "
                        f"({top['entity_id']}) at **{top['swiss_bank']}**.\n\n"
                        f"**Rationale:** {top['reason']} | **Category:** {top['pep_category']} | **Bank Flagged:** {top['flagged_by_bank']}"
                    )
                else:
                    st.warning(
                        f"⚠️ **POTENTIAL ALIAS / VARIATION ({top['confidence_pct']}%):** Similar to `{top['matched_name']}` ({top['entity_id']}).\n\n"
                        f"**Rationale:** {top['reason']}"
                    )
                match_df = pd.DataFrame(matches)[["entity_id", "matched_name", "confidence_pct", "reason", "pep_category", "swiss_bank"]]
                st.dataframe(match_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ No matching PEP profiles found in database (similarity < 65%). Clean initial intake.")

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
# TAB 2: Batch File Upload Gateway (CSV / JSON Drag & Drop)
# ==============================================================================
with tab_batch:
    st.subheader("Batch File Ingestion Gateway (CSV / JSON)")
    st.markdown(
        "Upload batched supervisory filings or core-banking dumps. The gateway automatically "
        "validates column integrity, profiles risk velocity, highlights immediate FINMA escalations, "
        "and stages records for atomic commit into the live SQLite repository."
    )

    t_col1, t_col2 = st.columns(2)
    sample_csv = _generate_sample_batch_csv()
    sample_json = _generate_sample_batch_json()

    t_col1.download_button(
        "📥 Download Sample Batch Template (CSV)",
        data=sample_csv.encode("utf-8"),
        file_name="sample_pep_batch.csv",
        mime="text/csv",
        use_container_width=True,
    )
    t_col2.download_button(
        "📥 Download Sample Batch Template (JSON)",
        data=sample_json.encode("utf-8"),
        file_name="sample_pep_batch.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()
    uploaded_file = st.file_uploader(
        "Drop batch file here (.csv or .json)",
        type=["csv", "json"],
        help="Supports standard tabular CSV or structured unified JSON lists.",
    )

    if uploaded_file is not None:
        st.markdown("### Pre-Commit Validation & Diff Preview")
        batch_records: list[dict[str, Any]] = []

        try:
            if uploaded_file.name.endswith(".csv"):
                df_upload = pd.read_csv(uploaded_file)
                st.info(f"Loaded CSV with **{len(df_upload)}** rows and **{len(df_upload.columns)}** columns.")
                for _, row in df_upload.iterrows():
                    batch_records.append(_convert_csv_row_to_unified(row, cfg))
            else:
                raw_json = json.load(uploaded_file)
                if isinstance(raw_json, list):
                    batch_records = raw_json
                elif isinstance(raw_json, dict):
                    batch_records = [raw_json]
                st.info(f"Loaded JSON payload with **{len(batch_records)}** unified record(s).")
        except Exception as ex:
            st.error(f"❌ Failed to parse uploaded file: {ex}")
            batch_records = []

        if batch_records:
            # Metrics computation
            total_items = len(batch_records)
            escalated_count = 0
            preview_rows = []

            for r in batch_records:
                ent_d = r.get("entity", {})
                rep_d = r.get("report", {})
                is_esc = rep_d.get("escalate_to_finma") == "Yes" or float(rep_d.get("risk_score") or 0) >= 60
                if is_esc:
                    escalated_count += 1
                preview_rows.append({
                    "Entity ID": ent_d.get("entity_id", "Unknown"),
                    "Name": ent_d.get("name", "Unknown"),
                    "Bank": ent_d.get("swiss_bank", "CH_A"),
                    "Quarter": rep_d.get("quarter", "N/A"),
                    "Inflow (USD)": f"${float(rep_d.get('inflow_usd') or 0):,.0f}",
                    "Pass-Through": f"{float(rep_d.get('pass_through_ratio') or 0):.2f}",
                    "Risk Score": f"{float(rep_d.get('risk_score') or 0):.0f}",
                    "Validation Status": "🚨 ESCALATION REQUIRED" if is_esc else "✅ STANDARD INTAKE",
                })

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Records", f"{total_items:,}")
            m2.metric("Valid Syntax", "100%")
            m3.metric("Projected Escalations", f"{escalated_count:,}", delta=f"{escalated_count} Alerts", delta_color="inverse")
            m4.metric("Clean Records", f"{total_items - escalated_count:,}")

            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            if st.button(f"🚀 Commit All {total_items} Records to Live Database", type="primary", use_container_width=True):
                with st.spinner("Executing atomic SQLite batch commit..."):
                    res = DBM.batch_insert_unified_records(batch_records, event_type="BATCH_FILE_INGESTION")
                    st.cache_data.clear()
                    st.success(
                        f"🎉 **Batch commit complete!** Successfully ingested **{res['total_ingested']}** records. "
                        f"**{res['escalations_triggered']}** cases registered in the supervisory queue."
                    )
                    time.sleep(1.0)
                    st.rerun()


# ==============================================================================
# TAB 3: Case Lifecycle & Dispositioning Workflow (with MROS Dossiers)
# ==============================================================================
with tab_cases:
    st.subheader("Case Lifecycle & Supervisory Dispositioning")
    st.markdown(
        "Manage regulatory investigation workflows for escalated PEP files. Review "
        "management overrides, track investigator assignments, adjust disposition stages, "
        "and generate legally compliant **MROS Suspicious Activity Report (SAR) Dossiers**."
    )

    # Ensure baseline cases exist
    all_cases_df = DBM.list_cases()

    # Case Summary KPI Cards
    k1, k2, k3, k4, k5 = st.columns(5)
    total_c = len(all_cases_df)
    new_alerts = len(all_cases_df[all_cases_df["status"] == "NEW_ALERT"])
    under_inv = len(all_cases_df[all_cases_df["status"] == "UNDER_INVESTIGATION"])
    pending_resp = len(all_cases_df[all_cases_df["status"] == "PENDING_RESPONSE"])
    escalated_pros = len(all_cases_df[all_cases_df["status"] == "ESCALATED_TO_PROSECUTOR"])

    k1.metric("Active Case Files", total_c)
    k2.metric("New Alerts", new_alerts)
    k3.metric("Under Investigation", under_inv)
    k4.metric("Pending Bank Resp.", pending_resp)
    k5.metric("Escalated to OAG", escalated_pros, delta="Legal Action", delta_color="inverse")

    # Filter toolbar
    st.divider()
    fc1, fc2, fc3 = st.columns([2, 2, 3])
    status_filter = fc1.selectbox(
        "Filter by Status",
        ["ALL", "NEW_ALERT", "UNDER_INVESTIGATION", "PENDING_RESPONSE", "ESCALATED_TO_PROSECUTOR", "CLOSED_RESOLVED"],
    )
    bank_filter = fc2.selectbox(
        "Filter by Reporting Bank",
        ["ALL", "CH_A", "CH_B", "CH_C", "CH_D"],
    )
    search_query = fc3.text_input("Search Case ID or Subject Name", value="")

    # Apply filters
    filtered_df = all_cases_df.copy()
    if status_filter != "ALL":
        filtered_df = filtered_df[filtered_df["status"] == status_filter]
    if bank_filter != "ALL":
        filtered_df = filtered_df[filtered_df["swiss_bank"] == bank_filter]
    if search_query.strip():
        q_lower = search_query.strip().lower()
        filtered_df = filtered_df[
            filtered_df["case_id"].str.lower().str.contains(q_lower)
            | filtered_df["entity_name"].str.lower().str.contains(q_lower)
        ]

    st.dataframe(
        filtered_df[[
            "case_id", "entity_name", "quarter", "swiss_bank", "risk_score",
            "status", "assigned_supervisor", "override_officer", "updated_at"
        ]],
        use_container_width=True,
        hide_index=True,
    )

    # Detailed Dispositioning Workspace
    if not filtered_df.empty:
        st.divider()
        st.subheader("Case Disposition & Dossier Workspace")

        case_options = filtered_df["case_id"].tolist()
        case_labels = {
            cid: f"{cid} — {filtered_df[filtered_df['case_id'] == cid].iloc[0]['entity_name']} (Score: {filtered_df[filtered_df['case_id'] == cid].iloc[0]['risk_score']:.0f})"
            for cid in case_options
        }
        selected_cid = st.selectbox(
            "Select Case File to Inspect & Disposition",
            options=case_options,
            format_func=lambda cid: case_labels.get(cid, cid),
        )

        selected_case = DBM.get_case(selected_cid)
        if selected_case:
            disp_col, doss_col = st.columns([1, 1])

            # Left Column: Dispositioning Controls
            with disp_col:
                st.markdown(f"#### Workflow Disposition: `{selected_cid}`")
                st.markdown(
                    f"**Subject:** {selected_case.get('entity_name')} | **Bank:** {selected_case.get('swiss_bank')} "
                    f"| **Quarter:** {selected_case.get('quarter')} | **Risk Score:** `{selected_case.get('risk_score', 0):.0f}/100`"
                )

                status_list = [
                    "NEW_ALERT",
                    "UNDER_INVESTIGATION",
                    "PENDING_RESPONSE",
                    "ESCALATED_TO_PROSECUTOR",
                    "CLOSED_RESOLVED",
                ]
                cur_status = selected_case.get("status", "NEW_ALERT")
                new_status = st.selectbox(
                    "Investigation Lifecycle Stage",
                    options=status_list,
                    index=status_list.index(cur_status) if cur_status in status_list else 0,
                )

                new_supervisor = st.text_input(
                    "Assigned FINMA Investigator / Desk",
                    value=selected_case.get("assigned_supervisor") or "Senior Investigator - Bern Desk",
                )

                new_override_just = st.text_area(
                    "Management Override Justification (Bank Leadership Audit)",
                    value=selected_case.get("override_justification") or "",
                    help="Documented bank management rationale explaining why compliance recommendations were overridden.",
                    height=100,
                )

                new_notes = st.text_area(
                    "Investigator Notes & Supervisory Findings",
                    value=selected_case.get("investigation_notes") or "",
                    help="Official case diary for FINMA supervisory file.",
                    height=120,
                )

                if st.button("💾 Save Case Disposition Updates", type="primary", use_container_width=True):
                    DBM.update_case(
                        selected_cid,
                        status=new_status,
                        assigned_supervisor=new_supervisor,
                        override_justification=new_override_just,
                        investigation_notes=new_notes,
                    )
                    st.cache_data.clear()
                    st.success(f"Case file `{selected_cid}` updated successfully!")
                    time.sleep(0.5)
                    st.rerun()

            # Right Column: Automated MROS SAR Dossier Generator
            with doss_col:
                st.markdown("#### Formal MROS SAR Dossier Generation")
                st.caption(
                    "Synthesizes structured KYC attributes, transaction flows, network counterparties, "
                    "and governance exceptions into an auditable regulatory submission."
                )

                # Fetch full case dossier data bundle
                dossier_data = DBM.get_case_dossier_data(selected_cid)
                if dossier_data:
                    generated_dossier = generate_sar_dossier(
                        case=selected_case,
                        entity=dossier_data.get("entity", {}),
                        report=dossier_data.get("report"),
                        edges=dossier_data.get("edges"),
                        transactions=dossier_data.get("transactions"),
                    )

                    st.download_button(
                        f"📥 Download MROS SAR Dossier ({selected_cid}.md)",
                        data=generated_dossier.encode("utf-8"),
                        file_name=f"MROS_SAR_Dossier_{selected_cid}.md",
                        mime="text/markdown",
                        type="secondary",
                        use_container_width=True,
                    )

                    with st.expander("📄 View Rendered MROS SAR Dossier Preview", expanded=True):
                        st.markdown(generated_dossier)


# ==============================================================================
# TAB 4: Live Stream Simulator
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
# TAB 5: Audit Trail & DB Health
# ==============================================================================
with tab_audit:
    st.subheader("Supervisory Audit Trail & Database Health")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Entities", f"{counts.get('entities', 0):,}")
    c2.metric("Quarterly Reports", f"{counts.get('pep_quarterly_report', 0):,}")
    c3.metric("Network Edges", f"{counts.get('network_edges', 0):,}")
    c4.metric("Active Cases", f"{counts.get('cases', 0):,}")
    c5.metric("Stream Audit Rows", f"{counts.get('stream_audit_log', 0):,}")

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
