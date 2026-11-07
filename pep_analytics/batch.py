"""CSV/JSON batch template generation and upload normalization."""
from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd

from pep_analytics import generator as GEN
from pep_analytics.config import RiskConfig
from pep_analytics.scoring import score_report


def _present(value: Any) -> bool:
    """Return whether an uploaded cell contains a usable value."""
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _text(row: pd.Series, column: str, default: str = "") -> str:
    value = row.get(column)
    return str(value).strip() if _present(value) else default


def _number(row: pd.Series, column: str, default: float = 0.0) -> float:
    value = row.get(column)
    if not _present(value):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Column '{column}' must contain numeric values.") from exc


def _integer(row: pd.Series, column: str, default: int = 0) -> int:
    return int(_number(row, column, float(default)))


def generate_sample_batch_csv() -> str:
    """Generate a tabular sample containing all supported PEP scenarios."""
    records = [
        GEN.generate_unified_record(key, quarter="2017Q1")
        for key in GEN.PRESET_NAMES
    ]
    rows = []
    for record in records:
        entity = record["entity"]
        edge = record["edge"]
        report = record["report"]
        rows.append({
            "entity_id": entity["entity_id"],
            "name": entity["name"],
            "entity_type": entity["entity_type"],
            "country": entity["country"],
            "pep_category": entity["pep_category"],
            "linked_pep_name": entity.get("linked_pep_name") or "",
            "swiss_bank": entity["swiss_bank"],
            "offshore_jurisdiction": entity["offshore_jurisdiction"],
            "flagged_as_pep_by_bank": entity["flagged_as_pep_by_bank"],
            "source_of_funds_verified": entity["source_of_funds_verified"],
            "quarter": report["quarter"],
            "inflow_usd": report["inflow_usd"],
            "outflow_usd": report["outflow_usd"],
            "cash_usd": report["cash_usd"],
            "pass_through_ratio": report["pass_through_ratio"],
            "management_overrides": report["management_overrides"],
            "days_alert_to_sar": report["days_alert_to_sar"],
            "target_name": edge["target_name"],
            "edge_type": edge["edge_type"],
            "known_to_bank": edge["known_to_bank"],
        })
    return pd.DataFrame(rows).to_csv(index=False)


def generate_sample_batch_json() -> str:
    """Generate structured sample records for every supported PEP scenario."""
    records = [
        GEN.generate_unified_record(key, quarter="2017Q1")
        for key in GEN.PRESET_NAMES
    ]
    return json.dumps(records, indent=2)


def convert_csv_row_to_unified(row: pd.Series, cfg: RiskConfig) -> dict[str, Any]:
    """Convert simplified or native quarterly-report CSV rows for persistence."""
    native_report = "volume_vs_expected" in row.index
    entity_id = _text(
        row, "entity_id", f"ENT-BATCH-{random.randint(1000, 9999)}"
    )
    name = _text(row, "name", "Unnamed Entity")
    quarter = _text(row, "quarter", "2017Q1")
    bank = _text(row, "swiss_bank", "CH_A")
    inflow = _number(row, "inflow_usd", 1_000_000.0)
    outflow = _number(row, "outflow_usd", 900_000.0)
    fallback_ratio = outflow / inflow if inflow else 0.0
    ratio = _number(row, "pass_through_ratio", fallback_ratio)
    overrides = _integer(row, "management_overrides")
    days_sar = _integer(row, "days_alert_to_sar")
    linked_pep_name = _text(row, "linked_pep_name") or None
    suspicious = _text(
        row,
        "is_suspicious",
        "Yes" if overrides or ratio >= 0.80 else "No",
    )
    scenario = _text(
        row,
        "scenario",
        "BATCH_QUARTERLY_REPORT" if native_report else "BATCH_CSV_INGESTION",
    )

    entity = {
        "entity_id": entity_id,
        "name": name,
        "entity_type": _text(row, "entity_type", "Company"),
        "country": _text(row, "country", "CH"),
        "pep_category": _text(row, "pep_category", "PEP-owned company"),
        "linked_pep_id": None,
        "linked_pep_name": linked_pep_name,
        "pep_role": "Public Official" if linked_pep_name else None,
        "flagged_as_pep_by_bank": _text(row, "flagged_as_pep_by_bank", "No"),
        "swiss_bank": bank,
        "offshore_jurisdiction": _text(row, "offshore_jurisdiction", "No"),
        "declared_income_usd": 250_000.0,
        "expected_monthly_volume_usd": 100_000.0,
        "source_of_funds_verified": _text(row, "source_of_funds_verified", "No"),
        "bank_risk_rating": "High" if overrides else "Medium",
        "is_suspicious": suspicious,
        "scenario": scenario,
    }
    edge = None if native_report else {
        "source_id": entity_id,
        "source_name": name,
        "target_id": f"TGT-{entity_id}",
        "target_name": _text(row, "target_name", "Counterparty Holding"),
        "edge_type": _text(row, "edge_type", "Money transfer"),
        "detail": "Batch file ingestion linkage",
        "total_usd": inflow,
        "txn_count": 1,
        "known_to_bank": _text(row, "known_to_bank", "Yes"),
        "found_via": "Batch Upload Gateway",
        "is_suspicious": entity["is_suspicious"],
    }
    report = {
        "quarter": quarter,
        "entity_id": entity_id,
        "name": name,
        "pep_category": entity["pep_category"],
        "linked_pep_name": entity["linked_pep_name"],
        "swiss_bank": bank,
        "flagged_as_pep_by_bank": entity["flagged_as_pep_by_bank"],
        "inflow_usd": inflow,
        "outflow_usd": outflow,
        "cash_usd": _number(row, "cash_usd"),
        "pass_through_ratio": ratio,
        "volume_vs_expected": _number(row, "volume_vs_expected", 2.5),
        "high_risk_destination_share": _number(
            row, "high_risk_destination_share", 0.5
        ),
        "n_counterparties": _number(row, "n_counterparties", 3),
        "alerts_raised": _number(
            row, "alerts_raised", 1 if days_sar else 0
        ),
        "compliance_recommended_exit_or_sar": _number(
            row, "compliance_recommended_exit_or_sar", 1 if overrides else 0
        ),
        "management_overrides": overrides,
        "introducer_assurance_used": _number(
            row, "introducer_assurance_used", 1 if overrides else 0
        ),
        "sar_filed": _number(row, "sar_filed", 1 if days_sar else 0),
        "days_alert_to_sar": days_sar,
        "source_of_funds_verified": entity["source_of_funds_verified"],
        "is_suspicious": suspicious,
        "scenario": scenario,
    }
    scored = score_report(pd.DataFrame([report]), cfg).iloc[0]
    report["risk_score"] = int(scored["risk_score"])
    report["risk_level"] = str(scored["risk_level"])
    report["escalate_to_finma"] = str(scored["escalate_to_finma"])
    return {"entity": entity, "edge": edge, "report": report, "transactions": []}


# --------------------------------------------------------------------------
# Network-edges uploads (bank-submitted relationship files)
# --------------------------------------------------------------------------
EDGE_COLUMNS = [
    "source_id", "source_name", "target_id", "target_name", "edge_type",
    "detail", "total_usd", "txn_count", "known_to_bank", "found_via",
    "is_suspicious",
]


def is_network_edges_frame(df: pd.DataFrame) -> bool:
    """Return True when an uploaded CSV is a network-edges file."""
    return {"source_id", "target_id"}.issubset(df.columns)


def convert_edges_frame(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalise a network-edges CSV into rows ready for ``network_edges``.

    Rows without both endpoints are dropped. ``known_to_bank`` defaults to
    "Yes" so that only rows the file explicitly marks "No" become hidden links.
    """
    edges: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        source_id = _text(row, "source_id")
        target_id = _text(row, "target_id")
        if not source_id or not target_id:
            continue
        total = row.get("total_usd")
        count = row.get("txn_count")
        edges.append({
            "source_id": source_id,
            "source_name": _text(row, "source_name", source_id),
            "target_id": target_id,
            "target_name": _text(row, "target_name", target_id),
            "edge_type": _text(row, "edge_type", "Unspecified"),
            "detail": _text(row, "detail") or None,
            "total_usd": _number(row, "total_usd") if _present(total) else None,
            "txn_count": _number(row, "txn_count") if _present(count) else None,
            "known_to_bank": _text(row, "known_to_bank", "Yes").capitalize(),
            "found_via": _text(row, "found_via", "Batch Upload Gateway"),
            "is_suspicious": _text(row, "is_suspicious", "No").capitalize(),
        })
    return edges
