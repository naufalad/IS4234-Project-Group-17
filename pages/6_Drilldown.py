"""Client drill-down page (Requirement 8).

Transactions over time, counterparties, immediate subgraph, and quarterly
risk history for a single entity.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from pep_analytics import graph as G
from pep_analytics.ui import get_scored, sidebar_config

st.title("Client drill-down")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

# ---- entity selector ----
ents = ds.entities[["entity_id", "name", "pep_category"]].drop_duplicates()
# Default to the highest-risk entity for a useful first view.
default_id = None
if not scored.empty:
    top = scored.sort_values("risk_score", ascending=False)
    default_id = top.iloc[0]["entity_id"] if not top.empty else None

labels = {f"{r['name']} ({r.entity_id}) · {r.pep_category}": r.entity_id
          for _, r in ents.iterrows()}
label_list = list(labels.keys())
default_idx = 0
if default_id is not None:
    for i, (lab, eid) in enumerate(labels.items()):
        if eid == default_id:
            default_idx = i
            break

pick = st.selectbox("Entity", label_list, index=default_idx)
entity_id = labels[pick]
profile = ds.entities[ds.entities["entity_id"] == entity_id].iloc[0]

# ---- profile card ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Entity type", str(profile.get("entity_type")))
c2.metric("Country", str(profile.get("country")))
c3.metric("Flagged by bank", str(profile.get("flagged_as_pep_by_bank")))
c4.metric("Source of funds", str(profile.get("source_of_funds_verified")))

# ---- transactions over time (Requirement 8.1) ----
st.subheader("Transactions over time")
txns = ds.transactions
mask = (txns["from_id"] == entity_id) | (txns["to_id"] == entity_id)
etx = txns[mask].copy()
if etx.empty:
    st.info("No transactions for this entity.")
else:
    etx["direction"] = etx.apply(
        lambda r: "Outgoing" if r["from_id"] == entity_id else "Incoming", axis=1
    )
    fig = px.scatter(
        etx, x="date", y="amount_usd", color="direction", symbol="type",
        hover_data=["from_name", "to_name", "purpose"],
        title="Transactions over time",
    )
    st.plotly_chart(fig, width='stretch')

    # ---- counterparties (Requirement 8.2) ----
    st.subheader("Counterparties")
    etx["counterparty"] = etx.apply(
        lambda r: r["to_name"] if r["from_id"] == entity_id else r["from_name"],
        axis=1,
    )
    cp = (
        etx.groupby(["counterparty", "direction"])["amount_usd"]
        .agg(["sum", "count"]).reset_index()
        .rename(columns={"sum": "total_usd", "count": "n_txns"})
        .sort_values("total_usd", ascending=False)
    )
    st.dataframe(cp, width='stretch', hide_index=True)

# ---- quarterly risk history (Requirement 8.4) ----
st.subheader("Quarterly risk history")
hist = scored[scored["entity_id"] == entity_id].sort_values("quarter")
if hist.empty:
    st.info("No quarterly report rows for this entity.")
else:
    cols = [c for c in ["quarter", "inflow_usd", "outflow_usd", "cash_usd",
                        "pass_through_ratio", "risk_score", "risk_level",
                        "escalate_to_finma"] if c in hist.columns]
    st.dataframe(hist[cols], width='stretch', hide_index=True)
    rfig = px.bar(hist, x="quarter", y="risk_score", color="risk_level",
                  color_discrete_map={"Low": "#74c69d", "Medium": "#f6ad55",
                                      "High": "#e57373"},
                  title="Risk score by quarter")
    st.plotly_chart(rfig, width='stretch')

# ---- immediate subgraph (Requirement 8.3) ----
st.subheader("Network subgraph")
full = G.build_graph(ds.entities, ds.network_edges, scored)
ego = G.ego_subgraph(full, entity_id, radius=1)
# ego_subgraph returns an undirected view; rebuild a directed subgraph for styling.
sub = full.subgraph(list(ego.nodes)).copy()
st.plotly_chart(G.plotly_figure(sub, f"Neighbourhood of {profile['name']}"),
                width='stretch')
