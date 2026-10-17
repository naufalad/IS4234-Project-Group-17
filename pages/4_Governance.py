"""Governance page — source-of-funds gaps, overrides, introducer reliance.

Requirements: 5.1, 5.2, 5.3 (exception lists), 5.4 (aggregate by bank/quarter).
Also surfaces the automated escalation records + export (Requirements 6.3, 6.5).
"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from pep_analytics import escalation, exceptions
from pep_app import get_scored, sidebar_config

st.title("Governance & exceptions")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

tab_sof, tab_over, tab_intro, tab_trend, tab_esc = st.tabs(
    ["Source of funds", "Overrides", "Introducer reliance", "Trends", "Escalations"]
)

with tab_sof:
    st.caption(
        f"PEP client-quarters with unverified source of funds and inflow "
        f"above ${cfg.sof_materiality_min:,.0f} (Requirement 5.1)."
    )
    sof = exceptions.sof_exceptions(scored, cfg)
    st.caption(f"{len(sof):,} exceptions.")
    st.dataframe(sof, use_container_width=True, hide_index=True)

with tab_over:
    st.caption(
        "Management overrode a compliance exit/SAR recommendation "
        "(Requirement 5.2) — the governance failure at the heart of the case."
    )
    ov = exceptions.override_exceptions(scored)
    st.caption(f"{len(ov):,} override-against-compliance events.")
    st.dataframe(ov, use_container_width=True, hide_index=True)

with tab_intro:
    st.caption("Decisions that relied on an introducer vouching (Requirement 5.3).")
    intro = exceptions.introducer_reliance(scored)
    st.caption(f"{len(intro):,} client-quarters relied on an introducer.")
    st.dataframe(intro, use_container_width=True, hide_index=True)

with tab_trend:
    st.caption("Exception counts by Swiss bank over time (Requirement 5.4).")
    agg = exceptions.aggregate_by_bank_quarter(scored, cfg)
    metric = st.selectbox(
        "Metric",
        ["sof_exceptions", "override_exceptions", "introducer_reliance"],
    )
    fig = px.line(agg, x="quarter", y=metric, color="swiss_bank", markers=True,
                  title=f"{metric} by bank over time")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(agg, use_container_width=True, hide_index=True)

with tab_esc:
    st.caption(
        "Automatically generated escalation records — no manual gate "
        "(Requirement 6). Triggered by risk score or SAR delay."
    )
    esc = escalation.build_escalations(scored, cfg)
    st.caption(f"{len(esc):,} escalation records.")
    st.dataframe(esc, use_container_width=True, hide_index=True)
    if not esc.empty:
        st.download_button(
            "Download escalation report (CSV)",
            data=escalation.to_csv(esc),
            file_name="finma_escalations.csv",
            mime="text/csv",
        )
