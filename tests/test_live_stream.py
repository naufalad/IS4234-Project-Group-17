"""Unit tests for live DB persistence, generator typologies, and streaming ingestion.

Run with:  pytest
"""
import tempfile
from pathlib import Path
import pytest

from pep_analytics import db as DBM
from pep_analytics import generator as GEN
from pep_analytics.data_loader import load_all


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database seeded from dataset2."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    DBM.init_db(temp_path, force_reseed=True)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_init_and_counts(temp_db):
    counts = DBM.get_counts(temp_db)
    assert counts["entities"] == 720
    assert counts["network_edges"] == 2658
    assert counts["transactions"] == 7354
    assert counts["pep_quarterly_report"] == 2084


def test_generator_presets_mirror_lebanon_typologies():
    for preset_key in ["COMMISSION_DIVERSION", "PROCUREMENT_KICKBACK", "FAMILY_STRUCTURING", "CLEAN_PEP_CONTROL"]:
        rec = GEN.generate_unified_record(preset_key, quarter="2016Q4")
        assert "entity" in rec
        assert "edge" in rec
        assert "report" in rec
        assert "transactions" in rec
        assert rec["entity"]["entity_id"].startswith("ENT-")
        assert rec["report"]["quarter"] == "2016Q4"

        # Check typology characteristics
        if preset_key == "COMMISSION_DIVERSION":
            assert rec["report"]["pass_through_ratio"] >= 0.95
            assert rec["report"]["management_overrides"] == 1
            assert rec["entity"]["flagged_as_pep_by_bank"] == "No"
            assert rec["report"]["risk_score"] >= 60
            assert rec["report"]["escalate_to_finma"] == "Yes"
        elif preset_key == "CLEAN_PEP_CONTROL":
            assert rec["entity"]["source_of_funds_verified"] == "Yes"
            assert rec["entity"]["flagged_as_pep_by_bank"] == "Yes"
            assert rec["report"]["risk_level"] == "Low"
            assert rec["report"]["escalate_to_finma"] == "No"


def test_insert_unified_record_updates_db(temp_db):
    rec = GEN.generate_unified_record("COMMISSION_DIVERSION", quarter="2016Q4", swiss_bank="CH_A")
    res = DBM.insert_unified_pep_record(
        entity=rec["entity"],
        edge=rec["edge"],
        report=rec["report"],
        transactions=rec["transactions"],
        event_type="CMS_MANUAL_ENTRY",
        db_path=temp_db,
    )
    assert res["status"] == "success"

    # Verify counts increased
    counts = DBM.get_counts(temp_db)
    assert counts["entities"] == 721
    assert counts["network_edges"] == 2659
    assert counts["transactions"] == 7355
    assert counts["pep_quarterly_report"] == 2085
    assert counts["stream_audit_log"] == 1

    # Verify audit log captures event
    audit = DBM.get_audit_log(limit=10, db_path=temp_db)
    assert len(audit) == 1
    assert audit.iloc[0]["event_type"] == "CMS_MANUAL_ENTRY"
    assert audit.iloc[0]["entity_id"] == rec["entity"]["entity_id"]


def test_load_all_reads_inserted_record(temp_db):
    rec = GEN.generate_unified_record("PROCUREMENT_KICKBACK", quarter="2016Q4")
    new_id = rec["entity"]["entity_id"]
    DBM.insert_unified_pep_record(
        entity=rec["entity"],
        edge=rec["edge"],
        report=rec["report"],
        transactions=rec["transactions"],
        db_path=temp_db,
    )

    ds = load_all(use_db=True, db_path=temp_db)
    assert new_id in set(ds.entities["entity_id"])
    assert new_id in set(ds.pep_quarterly_report["entity_id"])


def test_reset_db_to_baseline(temp_db):
    # Insert extra record
    rec = GEN.generate_unified_record("FAMILY_STRUCTURING", quarter="2016Q4")
    DBM.insert_unified_pep_record(
        entity=rec["entity"],
        edge=rec["edge"],
        report=rec["report"],
        transactions=rec["transactions"],
        db_path=temp_db,
    )
    assert DBM.get_counts(temp_db)["entities"] == 721

    # Reset
    DBM.reset_db_to_baseline(temp_db)
    counts = DBM.get_counts(temp_db)
    assert counts["entities"] == 720
    assert counts["pep_quarterly_report"] == 2084

