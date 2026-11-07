"""Tests for uploading bank-submitted network-edges CSVs."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from pep_analytics import db as DBM
from pep_analytics import graph as G
from pep_analytics.batch import convert_edges_frame, is_network_edges_frame

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    DBM.init_db(temp_path, force_reseed=True)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_detects_edges_file_and_not_quarterly_report():
    edges = pd.read_csv(REPO_ROOT / "dataset2" / "network_edges.csv", nrows=5)
    report = pd.read_csv(REPO_ROOT / "dataset2" / "pep_quarterly_report.csv", nrows=5)
    assert is_network_edges_frame(edges)
    assert not is_network_edges_frame(report)


def test_convert_drops_rows_without_endpoints_and_defaults_known_to_bank():
    df = pd.DataFrame([
        {"source_id": "A", "target_id": "B", "edge_type": "Owns", "known_to_bank": "no"},
        {"source_id": "A", "target_id": None, "edge_type": "Owns"},
        {"source_id": "C", "target_id": "D", "edge_type": "Family"},
    ])
    edges = convert_edges_frame(df)
    assert len(edges) == 2
    assert edges[0]["known_to_bank"] == "No"
    assert edges[1]["known_to_bank"] == "Yes"


def test_dataset2_edges_upload_adds_hidden_links_and_skips_duplicates(temp_db):
    df = pd.read_csv(REPO_ROOT / "dataset2" / "network_edges.csv")
    edges = convert_edges_frame(df)
    before = DBM.get_counts(temp_db)["network_edges"]

    first = DBM.insert_network_edges(edges, db_path=temp_db)
    assert first["hidden"] == 13
    assert first["inserted"] + first["skipped"] == len(edges)
    assert DBM.get_counts(temp_db)["network_edges"] == before + first["inserted"]

    second = DBM.insert_network_edges(edges, db_path=temp_db)
    assert second["inserted"] == 0
    assert second["skipped"] == len(edges)

    stored = DBM.load_table("network_edges", db_path=temp_db)
    assert len(G.hidden_edges(stored)) == 13
