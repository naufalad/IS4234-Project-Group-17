"""Network page — PEP network graph and cluster analytics.

Requirements: 1.1-1.4 (graph + hidden-link styling), 4.1-4.5 (clusters,
pass-through, blind spots, ranking).
"""
from __future__ import annotations

import streamlit as st

from pep_analytics import graph as G
from pep_app import get_scored, sidebar_config

st.title("Network")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

full = G.build_graph(ds.entities, ds.network_edges, scored)
pep_g = G.pep_subgraph(full)

st.caption(
    f"PEP-scoped graph: {pep_g.number_of_nodes():,} nodes, "
    f"{pep_g.number_of_edges():,} edges. "
    "Dashed red edges are links found by the regulator but not reported by the "
    "bank (known_to_bank = No)."
)

only_hidden = st.checkbox("Show only components containing hidden links", value=False)
graph_to_draw = pep_g
if only_hidden:
    hidden_nodes = set()
    for u, v, d in pep_g.edges(data=True):
        if d.get("is_hidden"):
            hidden_nodes.update([u, v])
    keep = set()
    ug = pep_g.to_undirected()
    for comp in __import__("networkx").connected_components(ug):
        if comp & hidden_nodes:
            keep |= comp
    graph_to_draw = pep_g.subgraph(keep).copy()

st.plotly_chart(G.plotly_figure(graph_to_draw, "PEP network"), use_container_width=True)

st.divider()

# ---- cluster ranking (Requirements 4.4, 4.5) ----
st.subheader("Cluster exposure ranking")
clusters = G.communities(pep_g)
ranking = G.rank_clusters(pep_g, clusters)
st.caption(
    "Exposure = aggregate money flow × (1 + hidden-link count) × (1 + peak risk). "
    "Clusters combining hidden links with high flow rank first."
)
st.dataframe(ranking, use_container_width=True, hide_index=True)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Bank blind spots")
    st.caption("PEP-linked entities the bank never flagged (Requirement 4.3).")
    bs = G.blind_spots(ds.entities)
    cols = [c for c in ["entity_id", "name", "pep_category", "linked_pep_name",
                        "swiss_bank"] if c in bs.columns]
    st.dataframe(bs[cols], use_container_width=True, hide_index=True)

with col2:
    st.subheader("Pass-through client-quarters")
    st.caption("Near-1 inflow/outflow ratio on material inflow (Requirement 4.2).")
    pt = G.pass_through_entities(scored, cfg)
    st.dataframe(pt, use_container_width=True, hide_index=True)

st.subheader("Hidden edges (regulator-found)")
he = G.hidden_edges(ds.network_edges)
cols = [c for c in ["source_name", "target_name", "edge_type", "detail",
                    "found_via", "total_usd"] if c in he.columns]
st.dataframe(he[cols], use_container_width=True, hide_index=True)
