"""Unit tests for entity resolution, case lifecycle management, batch ingestion, and SAR dossier generation.

Run with:  pytest tests/test_cases_and_resolution.py
"""
import tempfile
from pathlib import Path
import pandas as pd
import pytest

from pep_analytics import db as DBM
from pep_analytics import generator as GEN
from pep_analytics.dossier import generate_sar_dossier
from pep_analytics.entity_resolution import calculate_name_similarity, find_matching_entities


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database seeded from dataset2."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    DBM.init_db(temp_path, force_reseed=True)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_entity_resolution_exact_and_alias():
    # Exact match
    score, reason = calculate_name_similarity("Forry Associates", "Forry Associates")
    assert score == 1.0
    assert reason == "Exact match"

    # Initial contraction
    score, reason = calculate_name_similarity("R. Salameh", "Riad Salameh")
    assert score >= 0.85
    assert "Initial contraction" in reason

    # Corporate suffix stripping
    score, reason = calculate_name_similarity("Forry Associates Ltd", "Forry Associates S.A.")
    assert score >= 0.85

    # Completely different
    score, reason = calculate_name_similarity("John Doe", "Riad Salameh")
    assert score < 0.40


def test_find_matching_entities():
    df = pd.DataFrame([
        {"entity_id": "E1", "name": "Riad Salameh", "pep_category": "PEP", "swiss_bank": "CH_A"},
        {"entity_id": "E2", "name": "Raja Salameh", "pep_category": "PEP family", "swiss_bank": "CH_B"},
        {"entity_id": "E3", "name": "Marianne Hoayek", "pep_category": "PEP close associate", "swiss_bank": "CH_A"},
        {"entity_id": "E4", "name": "Credit Suisse Admin", "pep_category": "Not PEP", "swiss_bank": "CH_A"},
    ])

    matches = find_matching_entities("R. Salameh", df, threshold=0.70)
    assert len(matches) >= 1
    top_match = matches[0]
    assert "Salameh" in top_match["matched_name"]
    assert top_match["confidence_pct"] >= 70


def test_case_lifecycle_crud(temp_db):
    # Auto-seed cases from baseline escalations
    cases_df = DBM.list_cases(db_path=temp_db)
    assert not cases_df.empty
    assert "case_id" in cases_df.columns
    assert "status" in cases_df.columns

    # Fetch specific case
    cid = cases_df.iloc[0]["case_id"]
    case = DBM.get_case(cid, db_path=temp_db)
    assert case is not None
    assert case["case_id"] == cid

    # Update case status & supervisor notes
    success = DBM.update_case(
        cid,
        status="UNDER_INVESTIGATION",
        assigned_supervisor="Inspector General Mueller",
        investigation_notes="Subpoena served on Swiss Bank CH_A for beneficiary ledger.",
        override_justification="Overruled without EDD documentation by senior executive.",
        db_path=temp_db,
    )
    assert success is True

    # Verify updated values
    updated_case = DBM.get_case(cid, db_path=temp_db)
    assert updated_case["status"] == "UNDER_INVESTIGATION"
    assert updated_case["assigned_supervisor"] == "Inspector General Mueller"
    assert "Subpoena served" in updated_case["investigation_notes"]
    assert "Overruled without EDD" in updated_case["override_justification"]

    # Filter by status
    filtered = DBM.list_cases(status="UNDER_INVESTIGATION", db_path=temp_db)
    assert cid in filtered["case_id"].values


def test_batch_insert_unified_records(temp_db):
    rec1 = GEN.generate_unified_record("COMMISSION_DIVERSION", quarter="2017Q1")
    rec2 = GEN.generate_unified_record("CLEAN_PEP_CONTROL", quarter="2017Q1")

    res = DBM.batch_insert_unified_records([rec1, rec2], db_path=temp_db)
    assert res["status"] == "success"
    assert res["total_ingested"] == 2
    assert res["escalations_triggered"] == 1

    # Check that COMMISSION_DIVERSION was registered in cases table
    c_df = DBM.list_cases(db_path=temp_db)
    matching_case = c_df[c_df["entity_id"] == rec1["entity"]["entity_id"]]
    assert len(matching_case) == 1


def test_generate_sar_dossier():
    case = {
        "case_id": "CASE-2016Q4-ENT-TEST-999",
        "entity_id": "ENT-TEST-999",
        "quarter": "2016Q4",
        "risk_score": 85.0,
        "status": "ESCALATED_TO_PROSECUTOR",
        "assigned_supervisor": "Dr. Sarah Weber, AML Enforcement",
        "override_officer": "Executive Committee",
        "override_justification": "VIP commercial client status override",
        "investigation_notes": "Forensic audit confirmed sham brokerage contract.",
    }
    entity = {
        "entity_id": "ENT-TEST-999",
        "name": "Forry Offshore Ventures S.A.",
        "entity_type": "Company",
        "country": "VG",
        "swiss_bank": "CH_A",
        "pep_category": "PEP-owned company",
        "linked_pep_name": "Riad Salameh",
        "pep_role": "Central Bank Governor",
        "flagged_as_pep_by_bank": "No",
        "offshore_jurisdiction": "Yes",
        "source_of_funds_verified": "No",
    }
    report = {
        "quarter": "2016Q4",
        "inflow_usd": 15_000_000.0,
        "outflow_usd": 14_950_000.0,
        "pass_through_ratio": 0.997,
        "cash_usd": 0.0,
        "high_risk_destination_share": 0.85,
        "management_overrides": 2,
        "days_alert_to_sar": 120,
    }
    edges = [{
        "edge_type": "Money transfer",
        "target_name": "Banque du Liban",
        "known_to_bank": "No",
        "total_usd": 15_000_000.0,
    }]
    txns = [{
        "date": "2016-11-05",
        "type": "Wire Out",
        "amount_usd": 5_000_000.0,
        "from_name": "Forry Offshore Ventures S.A.",
        "from_country": "CH",
        "to_name": "Swiss Real Estate Holding",
        "to_country": "CH",
        "purpose": "Consultancy fee commission",
    }]

    dossier_text = generate_sar_dossier(case, entity, report, edges, txns)
    assert "# EIDGENÖSSISCHE FINANZMARKTAUFSICHT (FINMA)" in dossier_text
    assert "CASE-2016Q4-ENT-TEST-999" in dossier_text
    assert "Forry Offshore Ventures S.A." in dossier_text
    assert "REGULATORY BLIND SPOT DETECTED" in dossier_text
    assert "0.997" in dossier_text
    assert "Swiss Office of the Attorney General" in dossier_text

