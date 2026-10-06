# IS4234-Group-Project — AML Data Assurance Prototype

A prototype that detects **AML monitoring coverage gaps** by reconciling a bank's
core transaction feed against what its AML monitoring engine actually processed,
then flags, scores, assigns and escalates the gaps. It directly targets two
real-world failure modes: subsidiaries silently left out of monitoring scope
(the "Cayman branch" problem) and issues that get "warned about repeatedly but
nothing happens" (no escalation).

## Components

| File | Role |
|------|------|
| `reconcile.py` | **Reconciliation engine** — the prototype core. A scheduled job that compares the two feeds, builds scored flags, and runs escalation. |
| `app.py` | **Streamlit dashboard** — Management + Staff views over the engine's outputs. |
| `dataset/` | Input feeds and the engine's generated outputs. |

## Data

Inputs:

- `dataset/1_core_banking_transactions.csv` — core banking transactions (the source of truth).
- `dataset/3_aml_monitoring_processed.csv` — records the AML monitoring engine actually ingested.
- `dataset/2_unmonitored_transactions_gap.csv` — unmonitored txns pre-classified by root-cause reason code.
- `dataset/4_entity_registry.csv` — **authorised-entity registry**: the table of subsidiaries/branches allowed to transact and expected to be in monitoring scope. Entities transacting but *absent* here are flagged.

Outputs (written by `reconcile.py`, consumed by `app.py`):

- `dataset/flags.csv` — structured flag list: `flag_id, type, severity, txn_count, amount_usd, owner, opened_date, age_days, status`.
- `dataset/coverage_daily.csv` — `date, core_volume, monitored_volume` for the completeness-over-time chart.
- `dataset/entity_check.csv` — `booking_entity_id, booking_entity_name, authorised`.

`reconcile_state.db` (SQLite) holds the per-flag escalation state so countdown
timers persist across scheduled runs.

## Reconciliation engine (`reconcile.py`)

1. **Coverage reconciliation.** For every core transaction, check it exists in
   the monitoring feed by `txn_id`. Any core txn absent from monitoring is a
   **coverage gap**. Gaps are grouped into one flag per root cause.
2. **Entity registry check.** Compare every entity that *appears* in the
   transaction data against the authorised registry. Any transacting entity not
   in the registry is flagged — this is the **Cayman-subsidiary fix**.
3. **Severity scoring.** Each flag is scored **Red / Amber / Green** by its share
   of total unmonitored dollar volume *and* by the number of distinct accounts
   involved (breadth of exposure). Unauthorised-entity flags are always Red.
4. **Escalation.** Each flag gets an **owner** (routed by root cause) and a
   **countdown timer**. State is persisted in SQLite keyed by a stable flag
   identity, so a flag's age is tracked across runs. Once a flag is open longer
   than the SLA (default **30 days**), it **auto-escalates** to a higher tier.
   Resolved flags stay resolved.

### Run

```bash
pip install -r requirements.txt

python reconcile.py                      # reconcile at the simulated "today"
python reconcile.py --as-of 2026-07-05   # reconcile as if today were this date
python reconcile.py --sla-days 45        # override the escalation threshold
python reconcile.py --reset-state        # wipe the escalation state DB first
```

Schedule it on a timer (cron / Task Scheduler), e.g. nightly:

```cron
0 2 * * *  cd /path/to/repo && python reconcile.py >> reconcile.log 2>&1
```

### Dashboard

```bash
streamlit run app.py
```

The dashboard auto-detects `reconcile.py` outputs in `dataset/`; if they are not
present yet it falls back to computing a basic view from the raw feeds.
