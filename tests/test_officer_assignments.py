"""Tests for normalized officer-to-case assignment workflows."""
from __future__ import annotations

from pathlib import Path

from pep_analytics import db as DBM


def test_assign_and_update_critical_case(tmp_path: Path):
    db_path = tmp_path / "assignments.db"
    DBM.init_db(db_path)

    officers = DBM.list_officers(db_path)
    unassigned = DBM.list_unassigned_critical_cases(db_path=db_path)
    assert not officers.empty
    assert not unassigned.empty

    officer_id = officers.iloc[0]["officer_id"]
    case_id = unassigned.iloc[0]["case_id"]
    DBM.assign_officer_to_case(case_id, officer_id, "Initial handover", db_path)

    assignments = DBM.list_officer_cases(db_path)
    assignment = assignments[
        (assignments["case_id"] == case_id)
        & (assignments["officer_id"] == officer_id)
    ].iloc[0]
    assert assignment["status"] == "ASSIGNED"
    assert assignment["confirmed"] == 0
    assert assignment["notes"] == "Initial handover"
    assert case_id not in set(
        DBM.list_unassigned_critical_cases(db_path=db_path)["case_id"]
    )

    assert DBM.update_officer_case(
        case_id,
        officer_id,
        status="IN_PROGRESS",
        confirmed=True,
        notes="Ownership confirmed",
        db_path=db_path,
    )
    updated = DBM.list_officer_cases(db_path).iloc[0]
    assert updated["status"] == "IN_PROGRESS"
    assert updated["confirmed"] == 1
    assert updated["notes"] == "Ownership confirmed"


def test_add_officer_rejects_duplicate_identity(tmp_path: Path):
    db_path = tmp_path / "officers.db"
    DBM.init_db(db_path)
    DBM.add_officer("OFF-999", "Test Officer", "test@finma.example", db_path)

    try:
        DBM.add_officer("OFF-999", "Another Name", "other@finma.example", db_path)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Duplicate officer ID should be rejected")
