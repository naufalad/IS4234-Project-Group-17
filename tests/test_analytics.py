"""Unit tests for graph analytics, exceptions, escalation and review.

Run with:  pytest  (requires pandas + networkx).
Requirements: 4.2, 4.3, 5.1, 5.2, 6.1, 6.2, 7.3.
"""
import pandas as pd

from pep_analytics import escalation, exceptions, graph, review
from pep_analytics.config import RiskConfig
from pep_analytics.scoring import score_report


def _entities():
    return pd.DataFrame([
        dict(entity_id="P1", name="PEP One", entity_type="Person", country="LB",
             pep_category="PEP", linked_pep_id=None, linked_pep_name=None,
             pep_role="Minister", flagged_as_pep_by_bank="No", swiss_bank="CH_A",
             offshore_jurisdiction="No"),
        dict(entity_id="A1", name="Associate", entity_type="Person", country="CH",
             pep_category="PEP close associate", linked_pep_id="P1",
             linked_pep_name="PEP One", pep_role=None,
             flagged_as_pep_by_bank="Yes", swiss_bank="CH_A",
             offshore_jurisdiction="No"),
        dict(entity_id="N1", name="Normal Co", entity_type="Company", country="CH",
             pep_category="Not PEP", linked_pep_id=None, linked_pep_name=None,
             pep_role=None, flagged_as_pep_by_bank="No", swiss_bank="CH_B",
             offshore_jurisdiction="No"),
    ])


def _edges():
    return pd.DataFrame([
        dict(source_id="P1", source_name="PEP One", target_id="A1",
             target_name="Associate", edge_type="Close associate",
             detail="x", total_usd=None, txn_count=None, known_to_bank="No",
             found_via="Independent Review", is_suspicious="Yes"),
        dict(source_id="A1", source_name="Associate", target_id="N1",
             target_name="Normal Co", edge_type="Money transfer",
             detail="x", total_usd=500_000.0, txn_count=3, known_to_bank="Yes",
             found_via="Bank transaction report", is_suspicious="Yes"),
    ])


def _report():
    return pd.DataFrame([
        dict(quarter="2010Q1", entity_id="P1", name="PEP One", pep_category="PEP",
             linked_pep_name=None, swiss_bank="CH_A", flagged_as_pep_by_bank="No",
             inflow_usd=500_000, outflow_usd=480_000, cash_usd=0,
             pass_through_ratio=0.96, volume_vs_expected=8,
             high_risk_destination_share=0.7, n_counterparties=4, alerts_raised=0,
             compliance_recommended_exit_or_sar=1, management_overrides=1,
             introducer_assurance_used=1, sar_filed=0, days_alert_to_sar=120,
             source_of_funds_verified="No", is_suspicious="Yes"),
        dict(quarter="2010Q1", entity_id="A1", name="Associate",
             pep_category="PEP close associate", linked_pep_name="PEP One",
             swiss_bank="CH_A", flagged_as_pep_by_bank="Yes", inflow_usd=10_000,
             outflow_usd=0, cash_usd=0, pass_through_ratio=0.0,
             volume_vs_expected=0.5, high_risk_destination_share=0.0,
             n_counterparties=1, alerts_raised=0,
             compliance_recommended_exit_or_sar=0, management_overrides=0,
             introducer_assurance_used=0, sar_filed=0, days_alert_to_sar=0,
             source_of_funds_verified="Yes", is_suspicious="No"),
    ])


def test_blind_spots_only_unflagged_pep_linked():
    bs = graph.blind_spots(_entities())
    assert set(bs["entity_id"]) == {"P1"}  # A1 is flagged; N1 is not PEP-linked


def test_pass_through_detection():
    scored = score_report(_report(), RiskConfig())
    pt = graph.pass_through_entities(scored, RiskConfig())
    assert set(pt["entity_id"]) == {"P1"}


def test_hidden_edges_and_graph_flag():
    g = graph.build_graph(_entities(), _edges(), score_report(_report(), RiskConfig()))
    assert g["P1"]["A1"]["is_hidden"] is True
    assert g["A1"]["N1"]["is_hidden"] is False
    assert len(graph.hidden_edges(_edges())) == 1


def test_cluster_ranking_runs():
    g = graph.build_graph(_entities(), _edges(), score_report(_report(), RiskConfig()))
    clusters = graph.communities(g)
    ranking = graph.rank_clusters(g, clusters)
    assert "exposure_score" in ranking.columns
    assert len(ranking) >= 1


def test_sof_and_override_exceptions():
    scored = score_report(_report(), RiskConfig())
    sof = exceptions.sof_exceptions(scored, RiskConfig())
    assert set(sof["entity_id"]) == {"P1"}
    ov = exceptions.override_exceptions(scored)
    assert set(ov["entity_id"]) == {"P1"}


def test_escalation_score_and_sar_triggers():
    scored = score_report(_report(), RiskConfig())
    esc = escalation.build_escalations(scored, RiskConfig())
    assert "P1" in set(esc["entity_id"])
    reason = esc[esc["entity_id"] == "P1"].iloc[0]["trigger_reason"]
    assert "risk_score" in reason and "SAR delay" in reason  # both triggers fire


def test_review_worklist_scope_and_priority():
    scored = score_report(_report(), RiskConfig())
    wl = review.review_worklist(_entities(), _edges(), scored, RiskConfig())
    # Only PEP-linked entities (P1, A1); N1 excluded.
    assert set(wl["entity_id"]) == {"P1", "A1"}
    # P1 (blind spot + hidden link + high risk) ranks above A1.
    assert wl.iloc[0]["entity_id"] == "P1"
    assert bool(wl[wl["entity_id"] == "P1"].iloc[0]["is_blind_spot"]) is True
    assert bool(wl[wl["entity_id"] == "P1"].iloc[0]["has_hidden_link"]) is True
