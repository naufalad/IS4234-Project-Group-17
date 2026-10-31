"""Watchlist page — high-risk client-quarters with factor breakdown.

Requirements: 2.4 (filters), 3.6 (score breakdown).
"""
from __future__ import annotations

import streamlit as st

from pep_app import get_scored, sidebar_config

st.title("Watchlist")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

# ---- filters (Requirement 2.4) ----
col1, col2, col3, col4 = st.columns(4)
quarters = sorted(scored["quarter"].dropna().unique())
banks = sorted(scored["swiss_bank"].dropna().unique())
cats = sorted(scored["pep_category"].dropna().unique())
levels = ["High", "Medium", "Low"]

q_sel = col1.multiselect("Quarter", quarters)
b_sel = col2.multiselect("Swiss bank", banks)
c_sel = col3.multiselect("PEP category", cats)
l_sel = col4.multiselect("Risk level", levels, default=["High"])

view = scored.copy()
if q_sel:
    view = view[view["quarter"].isin(q_sel)]
if b_sel:
    view = view[view["swiss_bank"].isin(b_sel)]
if c_sel:
    view = view[view["pep_category"].isin(c_sel)]
if l_sel:
    view = view[view["risk_level"].isin(l_sel)]

view = view.sort_values("risk_score", ascending=False)

st.caption(f"{len(view):,} client-quarters match the current filters.")

display_cols = [
    "quarter", "entity_id", "name", "pep_category", "swiss_bank",
    "flagged_as_pep_by_bank", "inflow_usd", "pass_through_ratio",
    "risk_score", "risk_level", "escalate_to_finma",
]
display_cols = [c for c in display_cols if c in view.columns]
st.dataframe(view[display_cols], use_container_width=True, hide_index=True)

# ---- score breakdown for a selected row (Requirement 3.6) ----
st.subheader("Score breakdown")
if view.empty:
    st.info("No rows to break down.")
else:
    labels = {
        f"{r.quarter} · {r['name']} ({r.entity_id}) · score {r.risk_score}": i
        for i, r in view.reset_index(drop=True).iterrows()
    }
    pick = st.selectbox("Select a client-quarter", list(labels.keys()))
    row = view.reset_index(drop=True).iloc[labels[pick]]
    factors = row.get("score_factors") or []
    if not factors:
        st.write("No risk factors fired for this client-quarter (score 0).")
    else:
        import pandas as pd
        fdf = pd.DataFrame(factors, columns=["factor", "points"])
        st.table(fdf)
        st.write(f"**Total (capped at {cfg.score_cap}):** {row.risk_score} "
                 f"→ {row.risk_level}")
