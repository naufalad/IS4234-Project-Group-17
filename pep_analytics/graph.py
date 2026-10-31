"""PEP network graph construction, analytics and Plotly rendering.

Requirements:
  1.1-1.5 graph build + hidden-link styling + node colour + subgraph
  4.1 community/cluster detection
  4.2 pass-through chains
  4.3 bank blind spots (PEP-linked but not flagged)
  4.4-4.5 composite cluster ranking
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

from pep_analytics.config import RiskConfig

# Node colours by pep_category (Requirement 1.2).
PEP_CATEGORY_COLOURS = {
    "PEP": "#c0392b",
    "PEP family": "#e67e22",
    "PEP close associate": "#f1c40f",
    "PEP-owned company": "#8e44ad",
    "Not PEP": "#95a5a6",
}
PEP_LINKED_CATEGORIES = {
    "PEP", "PEP family", "PEP close associate", "PEP-owned company",
}


def _is_no(value) -> bool:
    return str(value).strip().lower() == "no"


def _is_yes(value) -> bool:
    return str(value).strip().lower() == "yes"


def build_graph(
    entities: pd.DataFrame,
    edges: pd.DataFrame,
    scored_report: pd.DataFrame | None = None,
) -> nx.DiGraph:
    """Build a directed graph with node and edge attributes.

    Node attrs: name, pep_category, flagged_as_pep_by_bank, swiss_bank,
    entity_type, country, is_pep_linked, risk_score (max across quarters if a
    scored report is supplied).
    Edge attrs: edge_type, detail, known_to_bank, total_usd, txn_count,
    is_hidden (True when known_to_bank == No, Requirement 1.3).
    """
    g = nx.DiGraph()

    # Per-entity peak risk score from the scored report (optional).
    risk_by_entity: dict[str, float] = {}
    if scored_report is not None and "risk_score" in scored_report.columns:
        risk_by_entity = (
            scored_report.groupby("entity_id")["risk_score"].max().to_dict()
        )

    for _, e in entities.iterrows():
        cat = e["pep_category"]
        g.add_node(
            e["entity_id"],
            name=e["name"],
            pep_category=cat,
            flagged_as_pep_by_bank=e.get("flagged_as_pep_by_bank"),
            swiss_bank=e.get("swiss_bank"),
            entity_type=e.get("entity_type"),
            country=e.get("country"),
            is_pep_linked=cat in PEP_LINKED_CATEGORIES,
            risk_score=float(risk_by_entity.get(e["entity_id"], 0.0)),
        )

    for _, r in edges.iterrows():
        src, tgt = r["source_id"], r["target_id"]
        # Add any endpoints missing from entities so edges are never dropped.
        for node, name in ((src, r.get("source_name")), (tgt, r.get("target_name"))):
            if node not in g:
                g.add_node(node, name=name, pep_category="Not PEP",
                           is_pep_linked=False, risk_score=0.0)
        total = r.get("total_usd")
        g.add_edge(
            src, tgt,
            edge_type=r.get("edge_type"),
            detail=r.get("detail"),
            known_to_bank=r.get("known_to_bank"),
            is_hidden=_is_no(r.get("known_to_bank")),
            total_usd=float(total) if pd.notna(total) else 0.0,
            txn_count=r.get("txn_count"),
        )
    return g


def pep_subgraph(g: nx.DiGraph) -> nx.DiGraph:
    """Graph restricted to PEP-linked nodes and anything directly linked to them.

    Requirement 1.1: the graph is scoped to PEPs and their connected entities.
    """
    seed = {n for n, d in g.nodes(data=True) if d.get("is_pep_linked")}
    keep = set(seed)
    for n in seed:
        keep.update(g.predecessors(n))
        keep.update(g.successors(n))
    return g.subgraph(keep).copy()


def ego_subgraph(g: nx.DiGraph, entity_id: str, radius: int = 1) -> nx.DiGraph:
    """Immediate neighbourhood of one entity (Requirements 1.5, 8.3)."""
    if entity_id not in g:
        return nx.DiGraph()
    return nx.ego_graph(g.to_undirected(as_view=True), entity_id, radius=radius)


# --------------------------------------------------------------------------
# Analytics (Requirement 4)
# --------------------------------------------------------------------------
def communities(g: nx.DiGraph) -> dict[str, int]:
    """Detect communities and return {node: cluster_id} (Requirement 4.1)."""
    ug = g.to_undirected()
    try:
        groups = nx.community.greedy_modularity_communities(ug)
    except Exception:
        groups = nx.connected_components(ug)
    mapping: dict[str, int] = {}
    for cid, members in enumerate(groups):
        for node in members:
            mapping[node] = cid
    return mapping


def blind_spots(entities: pd.DataFrame) -> pd.DataFrame:
    """PEP-linked entities the bank never flagged (Requirement 4.3)."""
    linked = entities[entities["pep_category"].isin(PEP_LINKED_CATEGORIES)]
    return linked[~linked["flagged_as_pep_by_bank"].apply(_is_yes)].copy()


def pass_through_entities(
    scored_report: pd.DataFrame, cfg: RiskConfig | None = None
) -> pd.DataFrame:
    """Client-quarters that look like pass-through (Requirement 4.2).

    Near-1 inflow/outflow ratio with material inflow -> money just passes
    through the account.
    """
    cfg = cfg or RiskConfig()
    df = scored_report
    ratio = pd.to_numeric(df["pass_through_ratio"], errors="coerce").fillna(0)
    inflow = pd.to_numeric(df["inflow_usd"], errors="coerce").fillna(0)
    mask = (ratio >= cfg.pass_through_ratio_min) & (inflow > cfg.pass_through_inflow_min)
    cols = [c for c in ["quarter", "entity_id", "name", "swiss_bank",
                        "inflow_usd", "outflow_usd", "pass_through_ratio",
                        "risk_score"] if c in df.columns]
    return df.loc[mask, cols].sort_values("inflow_usd", ascending=False)


def hidden_edges(edges: pd.DataFrame) -> pd.DataFrame:
    """Edges found only by the regulator / independent review (Requirement 1.3)."""
    return edges[edges["known_to_bank"].apply(_is_no)].copy()


def rank_clusters(
    g: nx.DiGraph,
    cluster_map: dict[str, int],
) -> pd.DataFrame:
    """Rank clusters by composite exposure (Requirements 4.4, 4.5).

    exposure = aggregate money-transfer flow
             x (1 + hidden_edge_count)        # hidden-link presence
             x (1 + max_risk / 100)           # peak client risk in the cluster
    """
    rows = []
    clusters = set(cluster_map.values())
    for cid in clusters:
        members = [n for n, c in cluster_map.items() if c == cid]
        mset = set(members)
        flow = 0.0
        hidden = 0
        for u, v, d in g.edges(members, data=True):
            if u in mset and v in mset:
                flow += d.get("total_usd", 0.0) or 0.0
                if d.get("is_hidden"):
                    hidden += 1
        max_risk = max((g.nodes[n].get("risk_score", 0.0) for n in members),
                       default=0.0)
        n_blind = sum(
            1 for n in members
            if g.nodes[n].get("is_pep_linked")
            and not _is_yes(g.nodes[n].get("flagged_as_pep_by_bank"))
        )
        exposure = flow * (1 + hidden) * (1 + max_risk / 100.0)
        rows.append({
            "cluster_id": cid,
            "n_entities": len(members),
            "total_flow_usd": flow,
            "hidden_edges": hidden,
            "blind_spot_entities": n_blind,
            "max_risk_score": max_risk,
            "exposure_score": exposure,
        })
    out = pd.DataFrame(rows).sort_values("exposure_score", ascending=False)
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# Rendering (Requirements 1.2, 1.3)
# --------------------------------------------------------------------------
def plotly_figure(g: nx.DiGraph, title: str = "PEP network"):
    """Render the graph with Plotly.

    Node colour by pep_category; hidden edges (known_to_bank == No) drawn as
    dashed red lines, visible edges as solid grey.
    """
    import plotly.graph_objects as go

    if g.number_of_nodes() == 0:
        return go.Figure().update_layout(title=f"{title} (no nodes)")

    pos = nx.spring_layout(g, seed=42, k=0.5)

    visible_x, visible_y = [], []
    hidden_x, hidden_y = [], []
    for u, v, d in g.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        if d.get("is_hidden"):
            hidden_x += [x0, x1, None]
            hidden_y += [y0, y1, None]
        else:
            visible_x += [x0, x1, None]
            visible_y += [y0, y1, None]

    edge_visible = go.Scatter(
        x=visible_x, y=visible_y, mode="lines",
        line=dict(width=0.6, color="#b0b0b0"), hoverinfo="none",
        name="Known to bank",
    )
    edge_hidden = go.Scatter(
        x=hidden_x, y=hidden_y, mode="lines",
        line=dict(width=1.6, color="#c0392b", dash="dash"), hoverinfo="none",
        name="Hidden (regulator-found)",
    )

    node_x, node_y, colours, texts = [], [], [], []
    for n, d in g.nodes(data=True):
        x, y = pos[n]
        node_x.append(x)
        node_y.append(y)
        colours.append(PEP_CATEGORY_COLOURS.get(d.get("pep_category"), "#95a5a6"))
        flagged = d.get("flagged_as_pep_by_bank")
        texts.append(
            f"{d.get('name', n)}<br>{d.get('pep_category')}"
            f"<br>flagged by bank: {flagged}"
            f"<br>risk: {d.get('risk_score', 0):.0f}"
        )
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers", hoverinfo="text", text=texts,
        marker=dict(size=9, color=colours, line=dict(width=0.5, color="#333")),
        name="Entities",
    )

    fig = go.Figure(data=[edge_visible, edge_hidden, node_trace])
    fig.update_layout(
        title=title, showlegend=True, hovermode="closest",
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig
