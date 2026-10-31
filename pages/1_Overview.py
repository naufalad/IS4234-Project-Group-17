"""Overview page — portfolio KPIs and risk level by bank (Requirements 2.4, 3.2)."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from pep_analytics import review, validation
from pep_app import get_scored, sidebar_config

st.title("Overview")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

def _num(col):
    import pandas as pd
    return pd.to_numeric(scored[col], errors="coerce").fillna(0)


# ---- KPIs (Requirement 4.1 in README's suggested overview) ----
overrides = int(_num("management_overrides").ge(1).sum())

c1, c2, c3 = st.columns(3)
c1.metric("PEP-linked clients", f"{scored['entity_id'].nunique():,}")
c2.metric("High-risk client-quarters", int((scored["risk_level"] == "High").sum()))
c3.metric("Management overrides", overrides)

st.divider()

# ---- risk level by bank ----
st.subheader("Risk level by Swiss bank")
by_bank = (
    scored.groupby(["swiss_bank", "risk_level"]).size().reset_index(name="count")
)
order = {"Medium": 1, "High": 2}
by_bank = by_bank.sort_values("risk_level", key=lambda s: s.map(order))
fig = px.bar(
    by_bank[by_bank["risk_level"].isin(["Medium", "High"])], x="swiss_bank", y="count", color="risk_level",
    color_discrete_map={"Medium": "#f6ad55", "High": "#e57373"},
    category_orders={"risk_level": ["Medium", "High"]},
    title="Client-quarters by risk level and bank",
)
st.plotly_chart(fig, use_container_width=True)

# # ---- escalations over time ----
# st.subheader("Escalations over time")
# esc = scored[scored["escalate_to_finma"] == "Yes"]
# if esc.empty:
#     st.info("No escalations under the current configuration.")
# else:
#     trend = esc.groupby("quarter").size().reset_index(name="escalations")
#     fig2 = px.line(trend, x="quarter", y="escalations", markers=True,
#                    title="Escalations per quarter")
#     st.plotly_chart(fig2, use_container_width=True)

# st.divider()

# ---- transaction-level coverage (Requirement 9.2) ----
st.subheader("Transaction-level: bank alerting vs suspicion")
tx = validation.transactions_missed_but_relevant(ds.transactions)
c1, c2, c3 = st.columns(3)
c1.metric("Suspicious transactions", tx["suspicious_total"])
c2.metric("Not alerted by bank", tx["suspicious_not_alerted_by_bank"])
c3.metric("Alerted by bank", tx["suspicious_alerted_by_bank"])

st.divider()

# ---- bank-missed-but-caught (Requirement 9.2) ----
st.subheader("Caught what the bank missed")
caught = validation.bank_missed_but_caught(scored)
st.caption(
    "Suspicious client-quarters that the bank did NOT flag as PEP-related but "
    "the analytics escalated."
)
st.metric("Bank-missed cases caught", len(caught))
st.dataframe(caught, use_container_width=True, hide_index=True)

st.divider()

# ---- independent KYC review worklist (Requirement 7) ----
st.subheader("Independent KYC review worklist")
st.caption(
    "Prioritised worklist for independent review of PEP accounts and their close "
    "associates (Jyske-bank reference model). Seeded by bank blind spots and "
    f"regulator-found hidden links; KYC refresh interval = "
    f"{cfg.kyc_review_interval_quarters} quarters."
)

wl = review.review_worklist(ds.entities, ds.network_edges, scored, cfg)

c1, c2, c3 = st.columns(3)
c1.metric("PEP accounts in scope", f"{len(wl):,}")
c2.metric("Due for KYC refresh", int(wl["due_for_refresh"].sum()))
c3.metric("Blind spots", int(wl["is_blind_spot"].sum()))

only_due = st.checkbox("Show only accounts due for refresh", value=False)
only_seeded = st.checkbox("Show only blind spots / hidden-link accounts", value=False)

review_view = wl
if only_due:
    review_view = review_view[review_view["due_for_refresh"]]
if only_seeded:
    review_view = review_view[
        review_view["is_blind_spot"] | review_view["has_hidden_link"]
    ]

st.dataframe(review_view, use_container_width=True, hide_index=True)

st.download_button(
    "Download review worklist (CSV)",
    data=review_view.to_csv(index=False).encode("utf-8"),
    file_name="kyc_review_worklist.csv",
    mime="text/csv",
)
