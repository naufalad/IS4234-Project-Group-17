"""SQLite database persistence and baseline seeder for PEP supervisory analytics.

Provides a persistent live storage layer initialized from ``dataset2/`` CSVs.
Supports single-entry CMS submissions, live streaming event ingestion,
audit logging, and instant reset back to baseline.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "dataset2"
DEFAULT_DB_PATH = REPO_ROOT / "pep_database.db"

# Schema definitions
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    name TEXT,
    entity_type TEXT,
    country TEXT,
    pep_category TEXT,
    linked_pep_id TEXT,
    linked_pep_name TEXT,
    pep_role TEXT,
    flagged_as_pep_by_bank TEXT,
    swiss_bank TEXT,
    offshore_jurisdiction TEXT,
    declared_income_usd REAL,
    expected_monthly_volume_usd REAL,
    source_of_funds_verified TEXT,
    bank_risk_rating TEXT,
    is_suspicious TEXT,
    scenario TEXT
);

CREATE TABLE IF NOT EXISTS network_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT,
    source_name TEXT,
    target_id TEXT,
    target_name TEXT,
    edge_type TEXT,
    detail TEXT,
    total_usd REAL,
    txn_count REAL,
    known_to_bank TEXT,
    found_via TEXT,
    is_suspicious TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id TEXT PRIMARY KEY,
    date TEXT,
    quarter TEXT,
    from_id TEXT,
    from_name TEXT,
    from_country TEXT,
    to_id TEXT,
    to_name TEXT,
    to_country TEXT,
    amount_usd REAL,
    type TEXT,
    purpose TEXT,
    swiss_bank TEXT,
    bank_raised_alert TEXT,
    is_suspicious TEXT,
    typology TEXT
);

CREATE TABLE IF NOT EXISTS pep_quarterly_report (
    quarter TEXT,
    entity_id TEXT,
    name TEXT,
    pep_category TEXT,
    linked_pep_name TEXT,
    swiss_bank TEXT,
    flagged_as_pep_by_bank TEXT,
    inflow_usd REAL,
    outflow_usd REAL,
    cash_usd REAL,
    pass_through_ratio REAL,
    volume_vs_expected REAL,
    high_risk_destination_share REAL,
    n_counterparties REAL,
    alerts_raised REAL,
    compliance_recommended_exit_or_sar REAL,
    management_overrides REAL,
    introducer_assurance_used REAL,
    sar_filed REAL,
    days_alert_to_sar REAL,
    source_of_funds_verified TEXT,
    risk_score REAL,
    risk_level TEXT,
    escalate_to_finma TEXT,
    is_suspicious TEXT,
    scenario TEXT,
    PRIMARY KEY (quarter, entity_id)
);

CREATE TABLE IF NOT EXISTS stream_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    event_type TEXT,
    entity_id TEXT,
    entity_name TEXT,
    quarter TEXT,
    swiss_bank TEXT,
    risk_score REAL,
    escalate_to_finma TEXT,
    trigger_reason TEXT,
    details TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    entity_id TEXT,
    entity_name TEXT,
    quarter TEXT,
    swiss_bank TEXT,
    risk_score REAL,
    status TEXT,
    assigned_supervisor TEXT,
    override_officer TEXT,
    override_justification TEXT,
    investigation_notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


def get_db_path(db_path: Path | str | None = None) -> Path:
    """Return database path, defaulting to pep_database.db in repo root."""
    return Path(db_path) if db_path else DEFAULT_DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a connection with WAL mode and foreign keys enabled."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _seed_table_from_csv(conn: sqlite3.Connection, table_name: str, csv_path: Path) -> None:
    """Populate an empty table from its dataset2 CSV file."""
    if not csv_path.exists():
        return
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return

        cols = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"

        # Convert empty strings to None/NULL where appropriate for numeric columns
        values = []
        for r in rows:
            row_vals = []
            for c in cols:
                val = r.get(c)
                if val == "":
                    val = None
                row_vals.append(val)
            values.append(row_vals)

        conn.executemany(sql, values)


def init_db(db_path: Path | str | None = None, force_reseed: bool = False) -> None:
    """Initialize SQLite database with schema and seed with dataset2/*.csv if empty."""
    path = get_db_path(db_path)
    conn = get_connection(path)
    with conn:
        if force_reseed:
            conn.executescript("""
                DROP TABLE IF EXISTS entities;
                DROP TABLE IF EXISTS network_edges;
                DROP TABLE IF EXISTS transactions;
                DROP TABLE IF EXISTS pep_quarterly_report;
                DROP TABLE IF EXISTS stream_audit_log;
                DROP TABLE IF EXISTS cases;
            """)

        conn.executescript(SCHEMA_SQL)

        # Check if tables have rows; if not, seed from CSVs
        cursor = conn.cursor()
        for table, file_name in [
            ("entities", "entities.csv"),
            ("network_edges", "network_edges.csv"),
            ("transactions", "transactions.csv"),
            ("pep_quarterly_report", "pep_quarterly_report.csv"),
        ]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            if count == 0:
                _seed_table_from_csv(conn, table, DATA_DIR / file_name)


def reset_db_to_baseline(db_path: Path | str | None = None) -> None:
    """Wipe database and re-seed clean baseline from dataset2/*.csv."""
    init_db(db_path=db_path, force_reseed=True)


def load_table(table_name: str, db_path: Path | str | None = None) -> pd.DataFrame:
    """Load a SQLite table into a pandas DataFrame, initializing DB if missing."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)

    conn = get_connection(path)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()
    return df


def get_counts(db_path: Path | str | None = None) -> dict[str, int]:
    """Return row counts for all managed tables."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)
    conn = get_connection(path)
    counts: dict[str, int] = {}
    try:
        cur = conn.cursor()
        for tbl in ["entities", "network_edges", "transactions", "pep_quarterly_report", "stream_audit_log", "cases"]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                counts[tbl] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts[tbl] = 0
    finally:
        conn.close()
    return counts


def get_audit_log(limit: int = 50, db_path: Path | str | None = None) -> pd.DataFrame:
    """Fetch recent live stream / CMS submission events."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)
    conn = get_connection(path)
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM stream_audit_log ORDER BY id DESC LIMIT {limit}",
            conn,
        )
    finally:
        conn.close()
    return df


def insert_unified_pep_record(
    entity: dict[str, Any],
    edge: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    transactions: list[dict[str, Any]] | None = None,
    event_type: str = "CMS_MANUAL_ENTRY",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Atomically insert or update a unified PEP lifecycle record into SQLite.

    Inserts:
      - entity into entities
      - optional edge into network_edges
      - optional report into pep_quarterly_report
      - optional transactions into transactions
      - audit log entry into stream_audit_log
    """
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)

    conn = get_connection(path)
    with conn:
        cur = conn.cursor()

        # 1. Entity
        ent_cols = [
            "entity_id", "name", "entity_type", "country", "pep_category",
            "linked_pep_id", "linked_pep_name", "pep_role", "flagged_as_pep_by_bank",
            "swiss_bank", "offshore_jurisdiction", "declared_income_usd",
            "expected_monthly_volume_usd", "source_of_funds_verified",
            "bank_risk_rating", "is_suspicious", "scenario",
        ]
        ent_data = {c: entity.get(c) for c in ent_cols}
        ent_sql = f"""
            INSERT OR REPLACE INTO entities ({", ".join(ent_cols)})
            VALUES ({", ".join(["?"] * len(ent_cols))})
        """
        cur.execute(ent_sql, [ent_data[c] for c in ent_cols])

        # 2. Network Edge (optional)
        if edge and edge.get("source_id") and edge.get("target_id"):
            edge_cols = [
                "source_id", "source_name", "target_id", "target_name", "edge_type",
                "detail", "total_usd", "txn_count", "known_to_bank", "found_via",
                "is_suspicious",
            ]
            edge_data = {c: edge.get(c) for c in edge_cols}
            edge_sql = f"""
                INSERT INTO network_edges ({", ".join(edge_cols)})
                VALUES ({", ".join(["?"] * len(edge_cols))})
            """
            cur.execute(edge_sql, [edge_data[c] for c in edge_cols])

        # 3. Quarterly Report (optional)
        if report and report.get("quarter") and report.get("entity_id"):
            rep_cols = [
                "quarter", "entity_id", "name", "pep_category", "linked_pep_name",
                "swiss_bank", "flagged_as_pep_by_bank", "inflow_usd", "outflow_usd",
                "cash_usd", "pass_through_ratio", "volume_vs_expected",
                "high_risk_destination_share", "n_counterparties", "alerts_raised",
                "compliance_recommended_exit_or_sar", "management_overrides",
                "introducer_assurance_used", "sar_filed", "days_alert_to_sar",
                "source_of_funds_verified", "risk_score", "risk_level",
                "escalate_to_finma", "is_suspicious", "scenario",
            ]
            rep_data = {c: report.get(c) for c in rep_cols}
            rep_sql = f"""
                INSERT OR REPLACE INTO pep_quarterly_report ({", ".join(rep_cols)})
                VALUES ({", ".join(["?"] * len(rep_cols))})
            """
            cur.execute(rep_sql, [rep_data[c] for c in rep_cols])

        # 4. Transactions (optional)
        if transactions:
            txn_cols = [
                "txn_id", "date", "quarter", "from_id", "from_name", "from_country",
                "to_id", "to_name", "to_country", "amount_usd", "type", "purpose",
                "swiss_bank", "bank_raised_alert", "is_suspicious", "typology",
            ]
            txn_sql = f"""
                INSERT OR REPLACE INTO transactions ({", ".join(txn_cols)})
                VALUES ({", ".join(["?"] * len(txn_cols))})
            """
            txn_vals = [[t.get(c) for c in txn_cols] for t in transactions]
            cur.executemany(txn_sql, txn_vals)

        # 5. Audit Log Entry
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        risk_score = report.get("risk_score") if report else 0.0
        escalate = report.get("escalate_to_finma") if report else "No"
        trigger_reason = ""
        if escalate == "Yes":
            trigger_reason = f"Risk Score {risk_score:.0f} >= threshold"

        log_sql = """
            INSERT INTO stream_audit_log (
                timestamp, event_type, entity_id, entity_name, quarter,
                swiss_bank, risk_score, escalate_to_finma, trigger_reason, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        details = f"Entity: {entity.get('name')}; Edge: {edge.get('edge_type') if edge else 'None'}; Inflow: ${report.get('inflow_usd', 0) if report else 0:,.0f}"
        cur.execute(
            log_sql,
            (
                now_iso,
                event_type,
                entity.get("entity_id"),
                entity.get("name"),
                report.get("quarter") if report else "",
                entity.get("swiss_bank"),
                risk_score,
                escalate,
                trigger_reason,
                details,
            ),
        )

        # 6. Auto-register case if escalated
        if escalate == "Yes":
            cid = f"CASE-{report.get('quarter', '2016')}-{entity.get('entity_id')}"
            cur.execute("""
                INSERT OR REPLACE INTO cases (
                    case_id, entity_id, entity_name, quarter, swiss_bank,
                    risk_score, status, assigned_supervisor, override_officer,
                    override_justification, investigation_notes, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, COALESCE((SELECT status FROM cases WHERE case_id = ?), 'NEW_ALERT'),
                    COALESCE((SELECT assigned_supervisor FROM cases WHERE case_id = ?), 'Senior Investigator - Bern Desk'),
                    ?, ?, ?,
                    COALESCE((SELECT created_at FROM cases WHERE case_id = ?), ?),
                    ?
                )
            """, (
                cid, entity.get("entity_id"), entity.get("name"),
                report.get("quarter", ""), entity.get("swiss_bank"),
                risk_score, cid, cid,
                "Head of Private Banking" if report.get("management_overrides", 0) >= 1 else None,
                "Overridden due to executive relationship assurance" if report.get("management_overrides", 0) >= 1 else None,
                "Automated intake from live supervisory alert.",
                cid, now_iso, now_iso,
            ))

    return {
        "status": "success",
        "entity_id": entity.get("entity_id"),
        "timestamp": now_iso,
        "escalate_to_finma": escalate,
    }


# ==============================================================================
# Case Lifecycle & Dispositioning Management
# ==============================================================================

def list_cases(status: str | None = None, db_path: Path | str | None = None) -> pd.DataFrame:
    """Return all cases, optionally filtered by status, auto-seeding if empty."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)

    auto_seed_cases_from_escalations(path)

    conn = get_connection(path)
    try:
        if status:
            df = pd.read_sql_query(
                "SELECT * FROM cases WHERE status = ? ORDER BY risk_score DESC, updated_at DESC",
                conn,
                params=[status],
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM cases ORDER BY risk_score DESC, updated_at DESC",
                conn,
            )
    finally:
        conn.close()
    return df


def get_case(case_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch a single case by case_id."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)
    conn = get_connection(path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cases WHERE case_id = ?", [case_id])
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_case_dossier_data(case_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    """Fetch complete case dossier bundle: case, entity, report, edges, transactions."""
    path = get_db_path(db_path)
    if not path.exists():
        init_db(path)
    conn = get_connection(path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cases WHERE case_id = ?", [case_id])
        case_row = cur.fetchone()
        if not case_row:
            return None
        case = dict(case_row)
        eid = case.get("entity_id")
        quarter = case.get("quarter")

        # Entity KYC
        cur.execute("SELECT * FROM entities WHERE entity_id = ?", [eid])
        ent_row = cur.fetchone()
        entity = dict(ent_row) if ent_row else {"entity_id": eid, "name": case.get("entity_name")}

        # Quarterly Report
        cur.execute("SELECT * FROM pep_quarterly_report WHERE entity_id = ? AND quarter = ?", [eid, quarter])
        rep_row = cur.fetchone()
        if not rep_row:
            cur.execute("SELECT * FROM pep_quarterly_report WHERE entity_id = ? ORDER BY quarter DESC LIMIT 1", [eid])
            rep_row = cur.fetchone()
        report = dict(rep_row) if rep_row else None

        # Network Edges
        cur.execute("SELECT * FROM network_edges WHERE source_id = ? OR target_id = ?", [eid, eid])
        edges = [dict(r) for r in cur.fetchall()]

        # Transactions
        cur.execute("SELECT * FROM transactions WHERE from_id = ? OR to_id = ? ORDER BY date DESC LIMIT 20", [eid, eid])
        transactions = [dict(r) for r in cur.fetchall()]

        return {
            "case": case,
            "entity": entity,
            "report": report,
            "edges": edges,
            "transactions": transactions,
        }
    finally:
        conn.close()


def update_case(
    case_id: str,
    status: str | None = None,
    assigned_supervisor: str | None = None,
    override_justification: str | None = None,
    investigation_notes: str | None = None,
    db_path: Path | str | None = None,
) -> bool:
    """Update fields on an existing case."""
    path = get_db_path(db_path)
    conn = get_connection(path)
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    updates = []
    params = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if assigned_supervisor is not None:
        updates.append("assigned_supervisor = ?")
        params.append(assigned_supervisor)
    if override_justification is not None:
        updates.append("override_justification = ?")
        params.append(override_justification)
    if investigation_notes is not None:
        updates.append("investigation_notes = ?")
        params.append(investigation_notes)

    if not updates:
        conn.close()
        return False

    updates.append("updated_at = ?")
    params.append(now_iso)
    params.append(case_id)

    with conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE cases SET {', '.join(updates)} WHERE case_id = ?", params)
        success = cur.rowcount > 0
    conn.close()
    return success


def auto_seed_cases_from_escalations(db_path: Path | str | None = None) -> None:
    """Seed initial cases table from high-risk / escalated reports if empty."""
    path = get_db_path(db_path)
    conn = get_connection(path)
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cases")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                SELECT quarter, entity_id, name, swiss_bank, risk_score, management_overrides
                FROM pep_quarterly_report
                WHERE escalate_to_finma = 'Yes' OR risk_score >= 60
                ORDER BY risk_score DESC
                LIMIT 30
            """)
            rows = cur.fetchall()
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cases_data = []
            for r in rows:
                cid = f"CASE-{r['quarter']}-{r['entity_id']}"
                has_ov = (r["management_overrides"] or 0) >= 1
                cases_data.append((
                    cid, r["entity_id"], r["name"], r["quarter"], r["swiss_bank"],
                    float(r["risk_score"] or 0.0),
                    "NEW_ALERT",
                    "Lead Financial Investigator - Zurich Desk",
                    "Head of Wealth Management" if has_ov else None,
                    "Client confirmed high-net-worth introducer backing" if has_ov else None,
                    "Automated intake from baseline supervisory escalation.",
                    now_iso, now_iso,
                ))
            if cases_data:
                cur.executemany("""
                    INSERT OR REPLACE INTO cases (
                        case_id, entity_id, entity_name, quarter, swiss_bank,
                        risk_score, status, assigned_supervisor, override_officer,
                        override_justification, investigation_notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, cases_data)
    conn.close()


def batch_insert_unified_records(
    records: list[dict[str, Any]],
    event_type: str = "BATCH_FILE_INGESTION",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Ingest a batch of records from uploaded file or external payload."""
    ingested = 0
    escalated = 0
    for rec in records:
        res = insert_unified_pep_record(
            entity=rec.get("entity", {}),
            edge=rec.get("edge"),
            report=rec.get("report"),
            transactions=rec.get("transactions"),
            event_type=event_type,
            db_path=db_path,
        )
        if res.get("status") == "success":
            ingested += 1
            if res.get("escalate_to_finma") == "Yes":
                escalated += 1

    return {
        "status": "success",
        "total_ingested": ingested,
        "escalations_triggered": escalated,
    }


