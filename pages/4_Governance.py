"""Governance page — source-of-funds gaps, overrides, introducer reliance.

Requirements: 5.1, 5.2, 5.3 (exception lists), 5.4 (aggregate by bank/quarter).
Also surfaces the automated escalation records + export (Requirements 6.3, 6.5).
"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from pep_analytics import escalation, exceptions
from pep_analytics.ui import get_scored, sidebar_config

st.title("Governance & exceptions")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

st.subheader("Exception counts by Swiss bank over time (Requirement 5.4).")
agg = exceptions.aggregate_by_bank_quarter(scored, cfg)
metric_labels = {
    "sof_exceptions": "Source-of-funds exceptions",
    "override_exceptions": "Override exceptions",
    "introducer_reliance": "Introducer reliance",
}
metric = st.selectbox(
    "Metric",
    list(metric_labels),
    format_func=metric_labels.get,
)
fig = px.line(agg, x="quarter", y=metric, color="swiss_bank", markers=True,
                title=f"{metric_labels.get(metric)} by bank over time")
st.plotly_chart(fig, width='stretch')
st.dataframe(agg, width='stretch', hide_index=True)


st.subheader("Source-of-funds exceptions (Requirement 5.1).")
st.caption(
    f"PEP client-quarters with unverified source of funds and inflow "
    f"above ${cfg.sof_materiality_min:,.0f} (Requirement 5.1)."
)
sof = exceptions.sof_exceptions(scored, cfg)
st.caption(f"{len(sof):,} exceptions.")
st.dataframe(sof, width='stretch', hide_index=True)

st.subheader("Override exceptions (Requirement 5.2).")
st.caption(
    "Management overrode a compliance exit/SAR recommendation "
    "(Requirement 5.2) — the governance failure at the heart of the case."
)
ov = exceptions.override_exceptions(scored)
st.caption(f"{len(ov):,} override-against-compliance events.")
st.dataframe(ov, width='stretch', hide_index=True)

st.subheader("Introducer reliance (Requirement 5.3).")
st.caption("Decisions that relied on an introducer vouching (Requirement 5.3).")
intro = exceptions.introducer_reliance(scored)
st.caption(f"{len(intro):,} client-quarters relied on an introducer.")
st.dataframe(intro, width='stretch', hide_index=True)

