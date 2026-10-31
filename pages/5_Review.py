"""Review page — independent KYC-review worklist (Requirement 7)."""
from __future__ import annotations

import streamlit as st

from pep_analytics import review
from pep_app import get_scored, sidebar_config

st.title("Independent KYC review worklist")

cfg = sidebar_config()
ds, scored = get_scored(cfg)

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

view = wl
if only_due:
    view = view[view["due_for_refresh"]]
if only_seeded:
    view = view[view["is_blind_spot"] | view["has_hidden_link"]]

st.dataframe(view, use_container_width=True, hide_index=True)

st.download_button(
    "Download review worklist (CSV)",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="kyc_review_worklist.csv",
    mime="text/csv",
)
