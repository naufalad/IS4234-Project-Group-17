"""CSV/JSON batch template generation and upload normalization."""
from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd

from pep_analytics import generator as GEN
from pep_analytics.config import RiskConfig
from pep_analytics.scoring import score_report


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
    """Convert one tabular upload row to the unified persistence structure."""
    entity_id = str(row.get("entity_id") or f"ENT-BATCH-{random.randint(1000, 9999)}")
    name = str(row.get("name") or "Unnamed Entity")
    quarter = str(row.get("quarter") or "2017Q1")
    bank = str(row.get("swiss_bank") or "CH_A")
    inflow = float(row.get("inflow_usd") or 1_000_000.0)
    outflow = float(row.get("outflow_usd") or 900_000.0)
    ratio = float(row.get("pass_through_ratio") or (outflow / inflow if inflow else 0.0))
    overrides = int(row.get("management_overrides") or 0)
    days_sar = int(row.get("days_alert_to_sar") or 0)

    entity = {
        "entity_id": entity_id,
        "name": name,
        "entity_type": str(row.get("entity_type") or "Company"),
        "country": str(row.get("country") or "CH"),
        "pep_category": str(row.get("pep_category") or "PEP-owned company"),
        "linked_pep_id": None,
        "linked_pep_name": str(row.get("linked_pep_name") or "") or None,
        "pep_role": "Public Official" if row.get("linked_pep_name") else None,
        "flagged_as_pep_by_bank": str(row.get("flagged_as_pep_by_bank") or "No"),
        "swiss_bank": bank,
        "offshore_jurisdiction": str(row.get("offshore_jurisdiction") or "No"),
        "declared_income_usd": 250_000.0,
        "expected_monthly_volume_usd": 100_000.0,
        "source_of_funds_verified": str(row.get("source_of_funds_verified") or "No"),
        "bank_risk_rating": "High" if overrides else "Medium",
        "is_suspicious": "Yes" if overrides or ratio >= 0.80 else "No",
        "scenario": "BATCH_CSV_INGESTION",
    }
    edge = {
        "source_id": entity_id,
        "source_name": name,
        "target_id": f"TGT-{entity_id}",
        "target_name": str(row.get("target_name") or "Counterparty Holding"),
        "edge_type": str(row.get("edge_type") or "Money transfer"),
        "detail": "Batch file ingestion linkage",
        "total_usd": inflow,
        "txn_count": 1,
        "known_to_bank": str(row.get("known_to_bank") or "Yes"),
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
        "cash_usd": float(row.get("cash_usd") or 0.0),
        "pass_through_ratio": ratio,
        "volume_vs_expected": 2.5,
        "high_risk_destination_share": 0.5,
        "n_counterparties": 3,
        "alerts_raised": 1 if days_sar else 0,
        "compliance_recommended_exit_or_sar": 1 if overrides else 0,
        "management_overrides": overrides,
        "introducer_assurance_used": 1 if overrides else 0,
        "sar_filed": 1 if days_sar else 0,
        "days_alert_to_sar": days_sar,
        "source_of_funds_verified": entity["source_of_funds_verified"],
        "is_suspicious": entity["is_suspicious"],
        "scenario": "BATCH_CSV_INGESTION",
    }
    scored = score_report(pd.DataFrame([report]), cfg).iloc[0]
    report["risk_score"] = int(scored["risk_score"])
    report["risk_level"] = str(scored["risk_level"])
    report["escalate_to_finma"] = str(scored["escalate_to_finma"])
    return {"entity": entity, "edge": edge, "report": report, "transactions": []}
