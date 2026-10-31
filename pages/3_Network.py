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

filter_col, entity_col = st.columns(2)
with filter_col:
    entity_type = st.selectbox(
        "Entity type",
        ["All", "Company", "Individual"],
        help="Choose a type, then select a specific entity to view its network.",
    )

type_value = {"Company": "Company", "Individual": "Person"}.get(entity_type)
candidates = [
    node_id
    for node_id, attrs in pep_g.nodes(data=True)
    if type_value is None or attrs.get("entity_type") == type_value
]
candidates.sort(key=lambda node_id: str(pep_g.nodes[node_id].get("name", node_id)))

with entity_col:
    selected_entity = st.selectbox(
        "Specific entity",
        [None, *candidates],
        format_func=lambda node_id: (
            "All entities"
            if node_id is None
            else f"{pep_g.nodes[node_id].get('name', node_id)} ({node_id})"
        ),
    )

graph_to_draw = pep_g
if selected_entity is not None:
    graph_to_draw = G.ego_subgraph(pep_g, selected_entity, radius=1)

only_hidden = st.checkbox("Show only components containing hidden links", value=False)
if only_hidden:
    hidden_nodes = set()
    for u, v, d in graph_to_draw.edges(data=True):
        if d.get("is_hidden"):
            hidden_nodes.update([u, v])
    keep = set()
    ug = graph_to_draw.to_undirected()
    for comp in __import__("networkx").connected_components(ug):
        if comp & hidden_nodes:
            keep |= comp
    graph_to_draw = graph_to_draw.subgraph(keep).copy()

nodes_col, edges_col = st.columns(2)
nodes_col.metric("Network nodes", f"{graph_to_draw.number_of_nodes():,}")
edges_col.metric("Network edges", f"{graph_to_draw.number_of_edges():,}")

st.caption(
    "Dashed red edges are links found by the regulator but not reported by the "
    "bank (known_to_bank = No)."
)

st.plotly_chart(G.plotly_figure(graph_to_draw, "PEP network"), use_container_width=True)

st.subheader("Hidden edges (regulator-found)")
he = G.hidden_edges(ds.network_edges)
visible_nodes = set(graph_to_draw.nodes)
he = he[
    he["source_id"].isin(visible_nodes) & he["target_id"].isin(visible_nodes)
]
cols = [c for c in ["source_name", "target_name", "edge_type", "detail",
                    "found_via", "total_usd"] if c in he.columns]
st.dataframe(he[cols], use_container_width=True, hide_index=True)

st.divider()

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
