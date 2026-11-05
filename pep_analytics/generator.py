"""Scenario-aware synthetic PEP data generator for dashboard.

Provides realistic presets mirroring the HSBC Lebanon / Forry case:
  - COMMISSION_DIVERSION: Offshore shell, nominee links, 98% pass-through, compliance override.
  - PROCUREMENT_KICKBACK: Government contractor, 8x volume, large cash structuring, high offshore share.
  - FAMILY_STRUCTURING: Unflagged PEP relative, hidden relationship, cash structuring.
  - CLEAN_PEP_CONTROL: Legitimate PEP benchmark with verified wealth, clean governance.
"""
from __future__ import annotations

import random
from typing import Any
import uuid

import pandas as pd

from pep_analytics.config import RiskConfig
from pep_analytics.scoring import score_report

PRESET_NAMES = {
    "COMMISSION_DIVERSION": "Central Bank Commission Diversion (Offshore Shell / Forry Model)",
    "PROCUREMENT_KICKBACK": "Public Procurement Kickback (Contractor Funneling)",
    "FAMILY_STRUCTURING": "Offshore Family Structuring (Unflagged Sibling / Cash)",
    "CLEAN_PEP_CONTROL": "Legitimate High-Net-Worth PEP (Benchmark / Control)",
}

_OFFSHORE_SHELLS = [
    ("Cedars Horizon Advisory Ltd", "VG", "BVI"),
    ("Levant Commercial Trust Corp", "PA", "Panama"),
    ("Orontes Capital Holdings Inc", "VG", "BVI"),
    ("Byblos Marine Consulting SA", "PA", "Panama"),
    ("Hermon Financial Intermediaries Ltd", "CY", "Cyprus"),
]

_CONTRACTORS = [
    ("Phoenicia Infrastructure Supplies SA", "LB"),
    ("Beirut Port Logistics Services SAL", "LB"),
    ("Mount Lebanon Civil Works SARL", "LB"),
    ("Metn Power & Engineering Co", "LB"),
]

_FAMILY_NAMES = [
    ("Nour El-Khoury", "Sister of PEP"),
    ("Karim Salameh", "Brother of Central Bank Governor"),
    ("Raya Chamoun", "Daughter of PEP"),
    ("Tarek Gemayel", "Cousin of Minister"),
]

_CLEAN_PEPS = [
    ("Dr. Selim Hobeika", "Member of Parliament"),
    ("Ambassador Leila Traboulsi", "Diplomat"),
    ("Judge Maroun Azar", "Appellate Court Magistrate"),
]

_SWISS_BANKS = ["CH_A", "CH_B", "CH_C", "CH_D"]


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def generate_unified_record(
    preset_key: str = "COMMISSION_DIVERSION",
    quarter: str = "2016Q4",
    swiss_bank: str | None = None,
    cfg: RiskConfig | None = None,
) -> dict[str, Any]:
    """Generate a cohesive (entity, edge, report, transactions) record bundle for a typology."""
    cfg = cfg or RiskConfig()
    bank = swiss_bank or random.choice(_SWISS_BANKS)

    if preset_key == "COMMISSION_DIVERSION":
        name, country, jur = random.choice(_OFFSHORE_SHELLS)
        entity_id = _uid("ENT-SHL")
        pep_id = _uid("PEP-BDL")
        pep_name = "R. K. Salameh"

        inflow = round(random.uniform(8_500_000, 18_000_000), 2)
        ratio = round(random.uniform(0.95, 0.99), 3)
        outflow = round(inflow * ratio, 2)
        exp_monthly = round(random.uniform(40_000, 80_000), 2)
        vol_vs_exp = round(inflow / (exp_monthly * 3), 2)

        entity = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": "Company",
            "country": country,
            "pep_category": "PEP-owned company",
            "linked_pep_id": pep_id,
            "linked_pep_name": pep_name,
            "pep_role": "Central Bank Governor",
            "flagged_as_pep_by_bank": "No",  # Bank blind spot!
            "swiss_bank": bank,
            "offshore_jurisdiction": "Yes",
            "declared_income_usd": 150_000.0,
            "expected_monthly_volume_usd": exp_monthly,
            "source_of_funds_verified": "No",
            "bank_risk_rating": "Medium",
            "is_suspicious": "Yes",
            "scenario": "S1_CENTRAL_BANK_COMMISSION_DIVERSION",
        }

        edge = {
            "source_id": pep_id,
            "source_name": pep_name,
            "target_id": entity_id,
            "target_name": name,
            "edge_type": "Nominee director",
            "detail": "Beneficial ownership concealed via bearer shares",
            "total_usd": inflow,
            "txn_count": random.randint(3, 8),
            "known_to_bank": "No",  # Regulator discovered hidden link!
            "found_via": "Independent Review",
            "is_suspicious": "Yes",
        }

        raw_report = {
            "quarter": quarter,
            "entity_id": entity_id,
            "name": name,
            "pep_category": "PEP-owned company",
            "linked_pep_name": pep_name,
            "swiss_bank": bank,
            "flagged_as_pep_by_bank": "No",
            "inflow_usd": inflow,
            "outflow_usd": outflow,
            "cash_usd": 0.0,
            "pass_through_ratio": ratio,
            "volume_vs_expected": vol_vs_exp,
            "high_risk_destination_share": round(random.uniform(0.80, 0.98), 2),
            "n_counterparties": random.randint(2, 5),
            "alerts_raised": 0,
            "compliance_recommended_exit_or_sar": 1,
            "management_overrides": 1,
            "introducer_assurance_used": 1,
            "sar_filed": 0,
            "days_alert_to_sar": 125,
            "source_of_funds_verified": "No",
            "is_suspicious": "Yes",
            "scenario": "S1_CENTRAL_BANK_COMMISSION_DIVERSION",
        }

    elif preset_key == "PROCUREMENT_KICKBACK":
        name, country = random.choice(_CONTRACTORS)
        entity_id = _uid("ENT-CTR")
        pep_id = _uid("PEP-MIN")
        pep_name = "Minister of Public Works"

        inflow = round(random.uniform(2_500_000, 6_000_000), 2)
        ratio = round(random.uniform(0.85, 0.92), 3)
        outflow = round(inflow * ratio, 2)
        cash = round(random.uniform(60_000, 220_000), 2)
        exp_monthly = round(random.uniform(100_000, 200_000), 2)
        vol_vs_exp = round(inflow / (exp_monthly * 3), 2)

        entity = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": "Company",
            "country": country,
            "pep_category": "PEP-owned company",
            "linked_pep_id": pep_id,
            "linked_pep_name": pep_name,
            "pep_role": "Cabinet Minister",
            "flagged_as_pep_by_bank": "No",
            "swiss_bank": bank,
            "offshore_jurisdiction": "No",
            "declared_income_usd": 500_000.0,
            "expected_monthly_volume_usd": exp_monthly,
            "source_of_funds_verified": "No",
            "bank_risk_rating": "Medium",
            "is_suspicious": "Yes",
            "scenario": "S2_PROCUREMENT_KICKBACK",
        }

        edge = {
            "source_id": entity_id,
            "source_name": name,
            "target_id": pep_id,
            "target_name": pep_name,
            "edge_type": "Money transfer",
            "detail": "Consultancy invoice payment",
            "total_usd": round(inflow * 0.35, 2),
            "txn_count": 4,
            "known_to_bank": "No",
            "found_via": "Forensic Audit",
            "is_suspicious": "Yes",
        }

        raw_report = {
            "quarter": quarter,
            "entity_id": entity_id,
            "name": name,
            "pep_category": "PEP-owned company",
            "linked_pep_name": pep_name,
            "swiss_bank": bank,
            "flagged_as_pep_by_bank": "No",
            "inflow_usd": inflow,
            "outflow_usd": outflow,
            "cash_usd": cash,
            "pass_through_ratio": ratio,
            "volume_vs_expected": vol_vs_exp,
            "high_risk_destination_share": round(random.uniform(0.60, 0.85), 2),
            "n_counterparties": random.randint(4, 8),
            "alerts_raised": 1,
            "compliance_recommended_exit_or_sar": 1,
            "management_overrides": 1,
            "introducer_assurance_used": 1,
            "sar_filed": 0,
            "days_alert_to_sar": 98,
            "source_of_funds_verified": "No",
            "is_suspicious": "Yes",
            "scenario": "S2_PROCUREMENT_KICKBACK",
        }

    elif preset_key == "FAMILY_STRUCTURING":
        name, relation = random.choice(_FAMILY_NAMES)
        entity_id = _uid("ENT-FAM")
        pep_id = _uid("PEP-GOV")
        pep_name = "Senior Political Official"

        inflow = round(random.uniform(450_000, 1_200_000), 2)
        ratio = round(random.uniform(0.82, 0.90), 3)
        outflow = round(inflow * ratio, 2)
        cash = round(random.uniform(55_000, 110_000), 2)
        exp_monthly = round(random.uniform(20_000, 40_000), 2)
        vol_vs_exp = round(inflow / (exp_monthly * 3), 2)

        entity = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": "Person",
            "country": "LB",
            "pep_category": "PEP family",
            "linked_pep_id": pep_id,
            "linked_pep_name": pep_name,
            "pep_role": relation,
            "flagged_as_pep_by_bank": "No",  # Unflagged family member
            "swiss_bank": bank,
            "offshore_jurisdiction": "No",
            "declared_income_usd": 80_000.0,
            "expected_monthly_volume_usd": exp_monthly,
            "source_of_funds_verified": "No",
            "bank_risk_rating": "Low",
            "is_suspicious": "Yes",
            "scenario": "S3_FAMILY_STRUCTURING",
        }

        edge = {
            "source_id": pep_id,
            "source_name": pep_name,
            "target_id": entity_id,
            "target_name": name,
            "edge_type": "Family",
            "detail": relation,
            "total_usd": None,
            "txn_count": None,
            "known_to_bank": "No",
            "found_via": "PEP Database",
            "is_suspicious": "Yes",
        }

        raw_report = {
            "quarter": quarter,
            "entity_id": entity_id,
            "name": name,
            "pep_category": "PEP family",
            "linked_pep_name": pep_name,
            "swiss_bank": bank,
            "flagged_as_pep_by_bank": "No",
            "inflow_usd": inflow,
            "outflow_usd": outflow,
            "cash_usd": cash,
            "pass_through_ratio": ratio,
            "volume_vs_expected": vol_vs_exp,
            "high_risk_destination_share": round(random.uniform(0.52, 0.75), 2),
            "n_counterparties": random.randint(3, 6),
            "alerts_raised": 0,
            "compliance_recommended_exit_or_sar": 0,
            "management_overrides": 0,
            "introducer_assurance_used": 1,
            "sar_filed": 0,
            "days_alert_to_sar": 0,
            "source_of_funds_verified": "No",
            "is_suspicious": "Yes",
            "scenario": "S3_FAMILY_STRUCTURING",
        }

    else:  # CLEAN_PEP_CONTROL
        name, role = random.choice(_CLEAN_PEPS)
        entity_id = _uid("ENT-CLN")
        pep_name = name

        inflow = round(random.uniform(40_000, 95_000), 2)
        ratio = round(random.uniform(0.40, 0.70), 3)
        outflow = round(inflow * ratio, 2)
        cash = round(random.uniform(0, 12_000), 2)
        exp_monthly = round(random.uniform(30_000, 50_000), 2)
        vol_vs_exp = round(inflow / (exp_monthly * 3), 2)

        entity = {
            "entity_id": entity_id,
            "name": name,
            "entity_type": "Person",
            "country": "LB",
            "pep_category": "PEP",
            "linked_pep_id": None,
            "linked_pep_name": None,
            "pep_role": role,
            "flagged_as_pep_by_bank": "Yes",  # Properly flagged
            "swiss_bank": bank,
            "offshore_jurisdiction": "No",
            "declared_income_usd": 320_000.0,
            "expected_monthly_volume_usd": exp_monthly,
            "source_of_funds_verified": "Yes",
            "bank_risk_rating": "Medium",
            "is_suspicious": "No",
            "scenario": "S4_LEGIT_PEP",
        }

        edge = {
            "source_id": entity_id,
            "source_name": name,
            "target_id": "GOV-LB-01",
            "target_name": "Lebanese Ministry of Justice",
            "edge_type": "Official role at",
            "detail": role,
            "total_usd": None,
            "txn_count": None,
            "known_to_bank": "Yes",
            "found_via": "Bank KYC",
            "is_suspicious": "No",
        }

        raw_report = {
            "quarter": quarter,
            "entity_id": entity_id,
            "name": name,
            "pep_category": "PEP",
            "linked_pep_name": None,
            "swiss_bank": bank,
            "flagged_as_pep_by_bank": "Yes",
            "inflow_usd": inflow,
            "outflow_usd": outflow,
            "cash_usd": cash,
            "pass_through_ratio": ratio,
            "volume_vs_expected": vol_vs_exp,
            "high_risk_destination_share": 0.05,
            "n_counterparties": random.randint(1, 3),
            "alerts_raised": 0,
            "compliance_recommended_exit_or_sar": 0,
            "management_overrides": 0,
            "introducer_assurance_used": 0,
            "sar_filed": 0,
            "days_alert_to_sar": 0,
            "source_of_funds_verified": "Yes",
            "is_suspicious": "No",
            "scenario": "S4_LEGIT_PEP",
        }

    # Automatically derive the supervisory risk score & factors
    scored_df = score_report(pd.DataFrame([raw_report]), cfg)
    row = scored_df.iloc[0]
    final_report = dict(raw_report)
    final_report["risk_score"] = int(row["risk_score"])
    final_report["risk_level"] = str(row["risk_level"])
    final_report["escalate_to_finma"] = str(row["escalate_to_finma"])

    # Optional linked transaction
    transactions = [
        {
            "txn_id": _uid("TXN"),
            "date": f"{quarter[:4]}-11-15",
            "quarter": quarter,
            "from_id": edge["source_id"],
            "from_name": edge["source_name"],
            "from_country": entity["country"],
            "to_id": edge["target_id"],
            "to_name": edge["target_name"],
            "to_country": "CH",
            "amount_usd": round(raw_report["inflow_usd"] * 0.45, 2),
            "type": "International wire",
            "purpose": edge["detail"] or "Inbound transfer",
            "swiss_bank": bank,
            "bank_raised_alert": "No",
            "is_suspicious": entity["is_suspicious"],
            "typology": "PEP_PASS_THROUGH" if preset_key == "COMMISSION_DIVERSION" else "Normal",
        }
    ]

    return {
        "entity": entity,
        "edge": edge,
        "report": final_report,
        "transactions": transactions,
        "score_factors": row.get("score_factors", []),
    }

