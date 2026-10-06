"""AML Data Assurance Dashboard (Streamlit).

Reads reconcile.py outputs from dataset/ if they exist:
    flags.csv, coverage_daily.csv, entity_check.csv
Otherwise falls back to computing a basic version straight from Syahir's files,
so the dashboard works before reconcile.py is finished.
"""
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

D = Path(__file__).parent / "dataset"
RED, AMBER, GREEN = "#f4a6a6", "#fbd38d", "#b7e4c7"

st.set_page_config(page_title="AML Data Assurance", layout="wide")


# ---------- data loading ----------
def fallback_from_raw():
    """TEMPORARY: replace with reconcile.py outputs once they exist."""
    core = pd.read_csv(D / "1_core_banking_transactions.csv", parse_dates=["txn_timestamp"])
    mon = pd.read_csv(D / "3_aml_monitoring_processed.csv")
    gap = pd.read_csv(D / "2_unmonitored_transactions_gap.csv", parse_dates=["txn_timestamp"])

    core["date"] = core["txn_timestamp"].dt.date
    core["monitored"] = core["txn_id"].isin(mon["txn_id"])

    daily = core.groupby("date").apply(
        lambda g: pd.Series({
            "core_volume": g["amount_usd"].sum(),
            "monitored_volume": g.loc[g["monitored"], "amount_usd"].sum(),
        }),
        include_groups=False,
    ).reset_index()

    # one flag per exclusion reason
    gap["date"] = gap["txn_timestamp"].dt.date
    f = gap.groupby("exclusion_reason_code").agg(
        txn_count=("txn_id", "count"),
        amount_usd=("amount_usd", "sum"),
        opened_date=("date", "min"),
    ).reset_index()
    today = core["date"].max()  # simulated "today" = last day in the data
    f["flag_id"] = [f"FLAG-{i + 1:03d}" for i in range(len(f))]
    f["type"] = "Coverage gap: " + f["exclusion_reason_code"]
    f["age_days"] = (pd.Timestamp(today) - pd.to_datetime(f["opened_date"])).dt.days
    share = f["amount_usd"] / f["amount_usd"].sum()
    f["severity"] = share.map(lambda s: "Red" if s >= 0.30 else "Amber" if s >= 0.10 else "Green")
    owners = ["Compliance Ops", "Data Engineering", "Financial Crime Risk"]
    f["owner"] = [owners[i % len(owners)] for i in range(len(f))]
    f["status"] = "Open"
    flags = f[["flag_id", "type", "severity", "txn_count", "amount_usd",
               "owner", "opened_date", "age_days", "status"]]

    # entity check: use a registry file if Syahir adds one, else infer from the gap file
    ents = core[["booking_entity_id", "booking_entity_name"]].drop_duplicates()
    reg_file = D / "4_entity_registry.csv"
    if reg_file.exists():
        reg = pd.read_csv(reg_file)
        ents["authorised"] = ents["booking_entity_id"].isin(reg.iloc[:, 0])
    else:
        bad = set(gap.loc[gap["exclusion_reason_code"] == "ENTITY_NOT_IN_SCOPE", "booking_entity_id"])
        ents["authorised"] = ~ents["booking_entity_id"].isin(bad)
    return flags, daily, ents


@st.cache_data
def load():
    needed = ["flags.csv", "coverage_daily.csv", "entity_check.csv"]
    if all((D / n).exists() for n in needed):
        flags = pd.read_csv(D / "flags.csv")
        daily = pd.read_csv(D / "coverage_daily.csv")
        ents = pd.read_csv(D / "entity_check.csv")
        # normalise `authorised` to real bools: a CSV may carry "True"/"False"
        # strings depending on the writer, and the entity check below relies on
        # `== False` / `is False` to spot unauthorised (e.g. Cayman) entities.
        ents["authorised"] = (
            ents["authorised"].astype(str).str.strip().str.lower()
            .isin(["true", "1", "yes"])
        )
        return flags, daily, ents, "reconcile.py outputs"
    flags, daily, ents = fallback_from_raw()
    return flags, daily, ents, "raw dataset files (fallback)"


flags, daily, entities, source = load()

# ---------- sidebar ----------
st.sidebar.title("AML Assurance")
view = st.sidebar.radio("View", ["Management", "Staff"])
using_reconcile = source.startswith("reconcile")
st.sidebar.caption(f"Data source: {source}")

flags = flags.copy()
if using_reconcile:
    # Escalation is decided by reconcile.py: trust its status as written.
    sla_days = None
else:
    # Fallback only: no reconcile output yet, so escalate here for demo purposes.
    sla_days = st.sidebar.slider("Escalation threshold (days)", 1, 60, 30)
    flags["status"] = flags.apply(
        lambda r: "Escalated" if (r["age_days"] > sla_days and r["status"] != "Resolved") else r["status"], axis=1)

daily = daily.copy()
daily["coverage_pct"] = daily["monitored_volume"] / daily["core_volume"] * 100
overall = daily["monitored_volume"].sum() / daily["core_volume"].sum() * 100
gap_value = daily["core_volume"].sum() - daily["monitored_volume"].sum()


def colour(v):
    return {"Red": f"background-color:{RED}", "Amber": f"background-color:{AMBER}",
            "Green": f"background-color:{GREEN}", "Escalated": f"background-color:{RED}"}.get(v, "")


# ---------- headline ----------
st.title("AML Data Assurance Dashboard")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Monitoring coverage (by value)", f"{overall:.1f}%")
c2.metric("Unmonitored value", f"${gap_value:,.0f}")
c3.metric("Open flags", int((flags["status"] != "Resolved").sum()))
c4.metric("Escalated flags", int((flags["status"] == "Escalated").sum()))

# ---------- completeness over time ----------
fig = px.line(daily, x="date", y="coverage_pct", title="Completeness over time (% of value monitored)")
fig.update_yaxes(range=[0, 105], title="Coverage %")
st.plotly_chart(fig, width="stretch")

# ---------- flags ----------
if view == "Management":
    esc = flags[flags["status"] == "Escalated"]
    st.subheader("Management summary")
    st.write(f"**{len(esc)} of {len(flags)} flags** are escalated, "
             f"covering **${esc['amount_usd'].sum():,.0f}** of unmonitored value.")
    bar = px.bar(flags.sort_values("amount_usd"), x="amount_usd", y="type", orientation="h",
                 color="severity", title="Unmonitored value by flag",
                 color_discrete_map={"Red": "#e57373", "Amber": "#f6ad55", "Green": "#74c69d"})
    bar.update_layout(yaxis_title="", xaxis_title="Unmonitored value (USD)")
    st.plotly_chart(bar, width="stretch")
    st.subheader("Escalated flags")
    cols = ["type", "severity", "amount_usd", "age_days", "owner"]
    if esc.empty:
        st.success("No escalated flags.")
    else:
        st.dataframe(esc[cols].style.map(colour, subset=["severity"]),
                     width="stretch", hide_index=True)
else:
    st.subheader("Flags to resolve")
    pick = st.multiselect("Filter by status", sorted(flags["status"].unique()),
                          default=list(flags["status"].unique()))
    shown = flags[flags["status"].isin(pick)]
    st.dataframe(shown.style.map(colour, subset=["severity", "status"]),
                 width="stretch", hide_index=True)

# ---------- entity registry ----------
unauth = entities[entities["authorised"] == False]
st.subheader("Entity registry check")
if view == "Management":
    if unauth.empty:
        st.success("All transacting entities are authorised.")
    else:
        name_col = next((c for c in ("booking_entity_name", "name") if c in unauth.columns), None)
        labels = [f"{r[name_col]} ({r['booking_entity_id']})" if name_col else str(r["booking_entity_id"])
                  for _, r in unauth.iterrows()]
        st.error(f"{len(unauth)} unauthorised entit{'y' if len(unauth) == 1 else 'ies'} transacting: "
                 + ", ".join(labels))
else:
    st.caption("Red = entity transacting outside the authorised registry")
    st.dataframe(
        entities.style.map(lambda v: f"background-color:{RED}" if v is False else "", subset=["authorised"]),
        width="stretch", hide_index=True)