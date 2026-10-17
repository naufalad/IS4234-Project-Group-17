"""Overview page — portfolio KPIs and risk level by bank (Requirements 2.4, 3.2)."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from pep_app import get_scored, sidebar_config

st.title("Overview")

cfg = sidebar_config()
ds, scored = get_scored(cfg)


def _num(col):
    import pandas as pd
    return pd.to_numeric(scored[col], errors="coerce").fillna(0)


# ---- KPIs (Requirement 4.1 in README's suggested overview) ----
total_inflow = _num("inflow_usd").sum()
overrides = int(_num("management_overrides").ge(1).sum())
days = _num("days_alert_to_sar")
avg_days = days[days > 0].mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("PEP-linked clients", f"{scored['entity_id'].nunique():,}")
c2.metric("High-risk client-quarters", int((scored["risk_level"] == "High").sum()))
c3.metric("Total PEP inflows", f"${total_inflow:,.0f}")
c4.metric("Management overrides", overrides)
c5.metric("Avg days alert→SAR", f"{avg_days:.0f}" if avg_days == avg_days else "—")

st.divider()

# ---- risk level by bank ----
st.subheader("Risk level by Swiss bank")
by_bank = (
    scored.groupby(["swiss_bank", "risk_level"]).size().reset_index(name="count")
)
order = {"Low": 0, "Medium": 1, "High": 2}
by_bank = by_bank.sort_values("risk_level", key=lambda s: s.map(order))
fig = px.bar(
    by_bank, x="swiss_bank", y="count", color="risk_level",
    color_discrete_map={"Low": "#74c69d", "Medium": "#f6ad55", "High": "#e57373"},
    category_orders={"risk_level": ["Low", "Medium", "High"]},
    title="Client-quarters by risk level and bank",
)
st.plotly_chart(fig, use_container_width=True)

# ---- escalations over time ----
st.subheader("Escalations over time")
esc = scored[scored["escalate_to_finma"] == "Yes"]
if esc.empty:
    st.info("No escalations under the current configuration.")
else:
    trend = esc.groupby("quarter").size().reset_index(name="escalations")
    fig2 = px.line(trend, x="quarter", y="escalations", markers=True,
                   title="Escalations per quarter")
    st.plotly_chart(fig2, use_container_width=True)
