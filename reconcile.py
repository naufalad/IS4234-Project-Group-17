"""AML Data Assurance - Reconciliation Engine.

A scheduled job (run on a timer, e.g. nightly cron / Task Scheduler) that
reconciles the CORE banking transaction feed against the AML MONITORING feed,
produces a structured list of flags with severity scores, assigns an owner and
a countdown timer to each flag, and auto-escalates flags left unresolved past
an SLA threshold.

Pipeline
--------
1. Load feeds              core banking txns + AML monitoring records + entity registry
2. Coverage reconciliation for every CORE txn, check it exists in MONITORING.
                          Missing => "coverage gap". Grouped into flags by root cause.
3. Entity registry check   transacting entities vs. the authorised-entity registry.
                          Any entity transacting outside the registry is flagged
                          (the Cayman-subsidiary fix).
4. Severity scoring        each flag scored Red / Amber / Green by $ volume share
                          and account-count involved.
5. Escalation             each flag gets an owner + a countdown timer. State is
                          persisted in a small SQLite DB so timers survive across
                          scheduled runs; a flag unresolved past SLA_DAYS (default
                          30) auto-escalates to a higher tier.

Outputs (written to dataset/, consumed by app.py)
-------------------------------------------------
    flags.csv           flag_id, type, severity, txn_count, amount_usd,
                        owner, opened_date, age_days, status
    coverage_daily.csv  date, core_volume, monitored_volume
    entity_check.csv    booking_entity_id, booking_entity_name, authorised

Run
---
    python reconcile.py                      # reconcile using the simulated "today"
    python reconcile.py --as-of 2026-09-15   # reconcile as if today were this date
    python reconcile.py --sla-days 45        # override the escalation threshold
    python reconcile.py --reset-state        # wipe the escalation state DB first
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DATASET_DIR = Path(__file__).parent / "dataset"
STATE_DB = Path(__file__).parent / "reconcile_state.db"

CORE_FILE = DATASET_DIR / "1_core_banking_transactions.csv"
MONITORING_FILE = DATASET_DIR / "3_aml_monitoring_processed.csv"
REGISTRY_FILE = DATASET_DIR / "4_entity_registry.csv"

FLAGS_OUT = DATASET_DIR / "flags.csv"
COVERAGE_OUT = DATASET_DIR / "coverage_daily.csv"
ENTITY_OUT = DATASET_DIR / "entity_check.csv"

# Escalation threshold: a flag open longer than this many days auto-escalates.
SLA_DAYS_DEFAULT = 30

# Severity thresholds by share of total unmonitored value.
SEV_RED = 0.30
SEV_AMBER = 0.10

# A flag with a large number of distinct accounts is at least Amber regardless
# of value (breadth of exposure matters, not just dollars).
ACCOUNT_COUNT_AMBER = 10
ACCOUNT_COUNT_RED = 25

# Owner routing: which team owns which root cause of a gap.
OWNER_BY_REASON = {
    "ENTITY_NOT_IN_SCOPE": "Financial Crime Risk",   # onboarding / scope decision
    "AFFILIATE_EXEMPT": "Financial Crime Risk",       # policy exemption to review
    "STD_RISK_COUNTRY_WIRE": "Compliance Ops",        # rule-tuning / disposition
    "FEED_FAILURE": "Data Engineering",               # technical pipeline break
}
OWNER_ENTITY = "Financial Crime Risk"
OWNER_DEFAULT = "Compliance Ops"

# Human-readable labels for each root cause.
TYPE_BY_REASON = {
    "ENTITY_NOT_IN_SCOPE": "Coverage gap: booking entity not in monitoring scope",
    "AFFILIATE_EXEMPT": "Coverage gap: affiliate-exemption rule excluding txns",
    "STD_RISK_COUNTRY_WIRE": "Coverage gap: standard-risk country wire exclusion",
    "FEED_FAILURE": "Coverage gap: monitoring feed ingestion failure",
}


# --------------------------------------------------------------------------- #
# 1. Load feeds
# --------------------------------------------------------------------------- #
def load_feeds():
    """Load the core, monitoring and registry feeds.

    Returns (core_df, monitoring_df, registry_df).
    """
    core = pd.read_csv(CORE_FILE, parse_dates=["txn_timestamp"])
    monitoring = pd.read_csv(MONITORING_FILE)

    if REGISTRY_FILE.exists():
        registry = pd.read_csv(REGISTRY_FILE)
    else:
        # No registry supplied: fall back to "entities that actually appear in
        # the monitoring feed are the authorised ones". This keeps the engine
        # working, but a real deployment should maintain 4_entity_registry.csv.
        authorised_ids = sorted(monitoring["booking_entity_id"].dropna().unique())
        registry = pd.DataFrame({
            "booking_entity_id": authorised_ids,
            "booking_entity_name": authorised_ids,
            "authorised": True,
        })
    return core, monitoring, registry


# --------------------------------------------------------------------------- #
# 2. Coverage reconciliation (transaction-level)
# --------------------------------------------------------------------------- #
def reconcile_coverage(core: pd.DataFrame, monitoring: pd.DataFrame):
    """For every CORE transaction, check it exists in MONITORING.

    Returns (core_with_flag, daily_coverage, missing) where:
        core_with_flag  core rows + boolean `monitored` column
        daily_coverage  per-day core vs monitored volume (for completeness chart)
        missing         core rows that are absent from the monitoring feed
    """
    monitored_ids = set(monitoring["txn_id"].dropna())
    core = core.copy()
    core["monitored"] = core["txn_id"].isin(monitored_ids)
    core["date"] = core["txn_timestamp"].dt.date

    daily = (
        core.groupby("date")
        .apply(
            lambda g: pd.Series({
                "core_volume": g["amount_usd"].sum(),
                "monitored_volume": g.loc[g["monitored"], "amount_usd"].sum(),
            }),
            include_groups=False,
        )
        .reset_index()
        .sort_values("date")
    )

    missing = core.loc[~core["monitored"]].copy()
    return core, daily, missing


def _reason_lookup(missing: pd.DataFrame) -> pd.DataFrame:
    """Attach a root-cause reason code to each missing (unmonitored) txn.

    Prefers the pre-classified exclusion_reason_code from the gap feed when
    available; otherwise every unexplained missing txn is treated as an
    UNEXPLAINED_GAP so nothing silently disappears.
    """
    gap_file = DATASET_DIR / "2_unmonitored_transactions_gap.csv"
    if gap_file.exists():
        gap = pd.read_csv(gap_file, usecols=["txn_id", "exclusion_reason_code"])
        reason_map = dict(zip(gap["txn_id"], gap["exclusion_reason_code"]))
    else:
        reason_map = {}

    missing = missing.copy()
    missing["reason_code"] = (
        missing["txn_id"].map(reason_map).fillna("UNEXPLAINED_GAP")
    )
    return missing


# --------------------------------------------------------------------------- #
# 3. Entity registry check (the Cayman-subsidiary fix)
# --------------------------------------------------------------------------- #
def check_entities(core: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Compare transacting entities against the authorised-entity registry.

    Any booking entity that appears in the transaction data but is not an
    authorised entity in the registry is marked authorised=False.
    """
    entities = (
        core[["booking_entity_id", "booking_entity_name"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    reg = registry.copy()
    if "authorised" in reg.columns:
        authorised_ids = set(
            reg.loc[reg["authorised"].astype(str).str.lower().isin(["true", "1", "yes"]),
                    "booking_entity_id"]
        )
    else:
        # Registry with no explicit flag: presence == authorised.
        authorised_ids = set(reg["booking_entity_id"])

    entities["authorised"] = entities["booking_entity_id"].isin(authorised_ids)
    return entities


# --------------------------------------------------------------------------- #
# 4. Flag generation + severity scoring
# --------------------------------------------------------------------------- #
def _severity(value_share: float, account_count: int) -> str:
    """Score a flag Red / Amber / Green by $ volume share and account breadth."""
    if value_share >= SEV_RED or account_count >= ACCOUNT_COUNT_RED:
        return "Red"
    if value_share >= SEV_AMBER or account_count >= ACCOUNT_COUNT_AMBER:
        return "Amber"
    return "Green"


def build_flags(missing: pd.DataFrame, entities: pd.DataFrame, as_of) -> pd.DataFrame:
    """Build the structured list of flags with severity, owner and opened_date.

    One flag per coverage-gap root cause, plus one flag per unauthorised entity.
    """
    missing = _reason_lookup(missing)
    total_value = missing["amount_usd"].sum() or 1.0  # avoid div-by-zero

    rows = []

    # --- coverage-gap flags, one per root cause ---------------------------- #
    for reason, grp in missing.groupby("reason_code"):
        value = float(grp["amount_usd"].sum())
        account_count = int(grp["account_id"].nunique()) if "account_id" in grp else 0
        opened = grp["date"].min()
        rows.append({
            "reason_code": reason,
            "type": TYPE_BY_REASON.get(reason, f"Coverage gap: {reason}"),
            "severity": _severity(value / total_value, account_count),
            "txn_count": int(len(grp)),
            "amount_usd": round(value, 2),
            "owner": OWNER_BY_REASON.get(reason, OWNER_DEFAULT),
            "opened_date": opened,
            "account_count": account_count,
        })

    # --- entity-registry flags, one per unauthorised transacting entity ---- #
    unauth = entities.loc[~entities["authorised"]]
    for _, ent in unauth.iterrows():
        ent_missing = missing.loc[missing.get("booking_entity_id") == ent["booking_entity_id"]] \
            if "booking_entity_id" in missing.columns else missing.iloc[0:0]
        value = float(ent_missing["amount_usd"].sum())
        opened = ent_missing["date"].min() if not ent_missing.empty else as_of.date()
        rows.append({
            "reason_code": f"ENTITY::{ent['booking_entity_id']}",
            "type": f"Unauthorised entity transacting: {ent['booking_entity_name']} "
                    f"({ent['booking_entity_id']})",
            # An entity transacting entirely outside the authorised registry is
            # always a Red control breach, independent of value.
            "severity": "Red",
            "txn_count": int(len(ent_missing)),
            "amount_usd": round(value, 2),
            "owner": OWNER_ENTITY,
            "opened_date": opened,
            "account_count": int(ent_missing["account_id"].nunique())
            if "account_id" in ent_missing else 0,
        })

    flags = pd.DataFrame(rows)
    if flags.empty:
        return flags

    # deterministic flag IDs, largest exposure first
    flags = flags.sort_values("amount_usd", ascending=False).reset_index(drop=True)
    flags["flag_id"] = [f"FLAG-{i + 1:03d}" for i in range(len(flags))]
    flags["opened_date"] = pd.to_datetime(flags["opened_date"])
    flags["age_days"] = (pd.Timestamp(as_of.date()) - flags["opened_date"]).dt.days
    return flags


# --------------------------------------------------------------------------- #
# 5. Escalation logic (owner + countdown timer, persisted across runs)
# --------------------------------------------------------------------------- #
def _init_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS flag_state (
            reason_code   TEXT PRIMARY KEY,  -- stable identity across runs
            first_seen    TEXT NOT NULL,     -- when this flag first opened
            status        TEXT NOT NULL,     -- Open | Escalated | Resolved
            owner         TEXT,
            resolved_date TEXT
        )
        """
    )
    conn.commit()


def apply_escalation(flags: pd.DataFrame, as_of, sla_days: int) -> pd.DataFrame:
    """Assign/track each flag's status via a persisted countdown timer.

    A flag keyed by its stable reason_code is remembered across scheduled runs.
    Each run recomputes days-open from the persisted first_seen date; once that
    exceeds sla_days and the flag is still open, it auto-escalates to a higher
    tier ("Escalated"). Resolved flags stay resolved.
    """
    if flags.empty:
        return flags

    conn = sqlite3.connect(STATE_DB)
    try:
        _init_state(conn)
        statuses, countdowns = [], []

        for _, row in flags.iterrows():
            key = row["reason_code"]
            opened = pd.to_datetime(row["opened_date"]).date().isoformat()

            cur = conn.execute(
                "SELECT first_seen, status, resolved_date FROM flag_state WHERE reason_code=?",
                (key,),
            ).fetchone()

            if cur is None:
                first_seen, status, resolved_date = opened, "Open", None
                conn.execute(
                    "INSERT INTO flag_state(reason_code, first_seen, status, owner) "
                    "VALUES (?,?,?,?)",
                    (key, first_seen, status, row["owner"]),
                )
            else:
                first_seen, status, resolved_date = cur

            # recompute age from the persisted first_seen so the timer is stable
            age_days = (as_of.date() - datetime.fromisoformat(first_seen).date()).days

            if status != "Resolved" and age_days > sla_days:
                status = "Escalated"

            # countdown timer: days remaining before (further) escalation
            days_remaining = max(sla_days - age_days, 0)

            conn.execute(
                "UPDATE flag_state SET status=?, owner=? WHERE reason_code=?",
                (status, row["owner"], key),
            )

            statuses.append(status)
            countdowns.append(days_remaining)

        conn.commit()
    finally:
        conn.close()

    flags = flags.copy()
    flags["status"] = statuses
    flags["days_to_escalation"] = countdowns
    return flags


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(as_of: datetime | None = None, sla_days: int = SLA_DAYS_DEFAULT,
        reset_state: bool = False) -> None:
    if reset_state and STATE_DB.exists():
        STATE_DB.unlink()

    core, monitoring, registry = load_feeds()

    # "today" for the reconciliation. Default to the last txn date in the data
    # (the dataset is a historical simulation), so age/escalation are meaningful.
    if as_of is None:
        as_of = pd.to_datetime(core["txn_timestamp"]).max().to_pydatetime()

    core, daily, missing = reconcile_coverage(core, monitoring)
    entities = check_entities(core, registry)
    flags = build_flags(missing, entities, as_of)
    flags = apply_escalation(flags, as_of, sla_days)

    # --- write the contract outputs consumed by app.py -------------------- #
    out_cols = ["flag_id", "type", "severity", "txn_count", "amount_usd",
                "owner", "opened_date", "age_days", "status"]
    if not flags.empty:
        flags_out = flags.copy()
        flags_out["opened_date"] = flags_out["opened_date"].dt.date
        flags_out[out_cols].to_csv(FLAGS_OUT, index=False)
    else:
        pd.DataFrame(columns=out_cols).to_csv(FLAGS_OUT, index=False)

    daily.to_csv(COVERAGE_OUT, index=False)
    entities[["booking_entity_id", "booking_entity_name", "authorised"]].to_csv(
        ENTITY_OUT, index=False
    )

    _print_summary(core, daily, flags, entities, as_of, sla_days)


def _print_summary(core, daily, flags, entities, as_of, sla_days) -> None:
    core_val = daily["core_volume"].sum()
    mon_val = daily["monitored_volume"].sum()
    coverage = (mon_val / core_val * 100) if core_val else 0.0
    unauth = entities.loc[~entities["authorised"]]

    print("=" * 68)
    print("AML RECONCILIATION ENGINE")
    print(f"  as-of date            : {as_of.date()}")
    print(f"  SLA / escalation days : {sla_days}")
    print("-" * 68)
    print(f"  core transactions     : {len(core)}")
    print(f"  monitored transactions: {int(core['monitored'].sum())}")
    print(f"  coverage by value     : {coverage:.1f}%")
    print(f"  unmonitored value     : ${core_val - mon_val:,.2f}")
    print("-" * 68)
    print(f"  flags raised          : {len(flags)}")
    if not flags.empty:
        print(f"    open                : {(flags['status'] == 'Open').sum()}")
        print(f"    escalated           : {(flags['status'] == 'Escalated').sum()}")
        print(f"    resolved            : {(flags['status'] == 'Resolved').sum()}")
        print("-" * 68)
        for _, f in flags.iterrows():
            print(f"  [{f['flag_id']}] {f['severity']:5} {f['status']:9} "
                  f"${f['amount_usd']:>14,.2f}  age={f['age_days']:>3}d  "
                  f"-> {f['owner']}")
            print(f"           {f['type']}")
    print("-" * 68)
    print(f"  transacting entities  : {len(entities)}")
    print(f"  unauthorised entities : {len(unauth)}")
    for _, e in unauth.iterrows():
        print(f"    FLAGGED: {e['booking_entity_name']} ({e['booking_entity_id']})")
    print("=" * 68)
    print(f"wrote: {FLAGS_OUT.name}, {COVERAGE_OUT.name}, {ENTITY_OUT.name}")


def _parse_args():
    p = argparse.ArgumentParser(description="AML reconciliation engine")
    p.add_argument("--as-of", type=lambda s: datetime.fromisoformat(s),
                   default=None, help="Reconcile as if today were this date (YYYY-MM-DD)")
    p.add_argument("--sla-days", type=int, default=SLA_DAYS_DEFAULT,
                   help="Days before an unresolved flag auto-escalates")
    p.add_argument("--reset-state", action="store_true",
                   help="Wipe the escalation state DB before running")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(as_of=args.as_of, sla_days=args.sla_days, reset_state=args.reset_state)
