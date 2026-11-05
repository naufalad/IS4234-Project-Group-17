"""Validation page — detection quality vs the answer key (Requirement 9).

This is the only page that reads is_suspicious / scenario / typology.
"""
from __future__ import annotations

import streamlit as st

from pep_analytics import validation
from pep_analytics.ui import get_scored, sidebar_config

st.title("Detection-quality validation")

st.warning(
    "This page uses the answer-key columns (is_suspicious / scenario / typology) "
    "ONLY to measure detection quality. They never feed the risk score, graph "
    "analytics, or escalation."
)

cfg = sidebar_config()
ds, scored = get_scored(cfg)

# ---- escalation precision/recall (Requirement 9.1) ----
metrics = validation.evaluate_escalations(scored)
m = metrics.as_dict()

st.subheader("Escalation vs ground truth (client-quarters)")
c1, c2, c3 = st.columns(3)
c1.metric("Precision", f"{m['precision']:.0%}")
c2.metric("Recall", f"{m['recall']:.0%}")
c3.metric("F1", f"{m['f1']:.2f}")

c4, c5, c6, c7 = st.columns(4)
c4.metric("True positives", m["true_positives"])
c5.metric("False positives", m["false_positives"])
c6.metric("False negatives", m["false_negatives"])
c7.metric("True negatives", m["true_negatives"])

st.divider()

# ---- bank-missed-but-caught (Requirement 9.2) ----
st.subheader("Caught what the bank missed")
caught = validation.bank_missed_but_caught(scored)
st.caption(
    "Suspicious client-quarters that the bank did NOT flag as PEP-related but "
    "the analytics escalated."
)
st.metric("Bank-missed cases caught", len(caught))
st.dataframe(caught, width='stretch', hide_index=True)

st.divider()

# ---- transaction-level coverage (Requirement 9.2) ----
st.subheader("Transaction-level: bank alerting vs suspicion")
tx = validation.transactions_missed_but_relevant(ds.transactions)
c1, c2, c3 = st.columns(3)
c1.metric("Suspicious transactions", tx["suspicious_total"])
c2.metric("Not alerted by bank", tx["suspicious_not_alerted_by_bank"])
c3.metric("Alerted by bank", tx["suspicious_alerted_by_bank"])
