"""Load, type-coerce and validate the four tables from SQLite or ``dataset2/``.

Requirements: 2.1, 2.2 (ingestion), 2.3 (readable validation errors),
10.1 (reads from ``dataset2/`` as baseline), plus dynamic live SQLite backing.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pep_analytics import db as DBM

# dataset2/ lives next to the repo root (one level up from this package).
DATA_DIR = Path(__file__).resolve().parent.parent / "dataset2"

# Columns we rely on downstream. Extra columns are allowed; missing ones error.
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "entities": [
        "entity_id", "name", "entity_type", "country", "pep_category",
        "linked_pep_id", "linked_pep_name", "pep_role", "flagged_as_pep_by_bank",
        "swiss_bank", "offshore_jurisdiction", "declared_income_usd",
        "expected_monthly_volume_usd", "source_of_funds_verified",
        "bank_risk_rating", "is_suspicious", "scenario",
    ],
    "network_edges": [
        "source_id", "source_name", "target_id", "target_name", "edge_type",
        "detail", "total_usd", "txn_count", "known_to_bank", "found_via",
        "is_suspicious",
    ],
    "transactions": [
        "txn_id", "date", "quarter", "from_id", "from_name", "from_country",
        "to_id", "to_name", "to_country", "amount_usd", "type", "purpose",
        "swiss_bank", "bank_raised_alert", "is_suspicious", "typology",
    ],
    "pep_quarterly_report": [
        "quarter", "entity_id", "name", "pep_category", "linked_pep_name",
        "swiss_bank", "flagged_as_pep_by_bank", "inflow_usd", "outflow_usd",
        "cash_usd", "pass_through_ratio", "volume_vs_expected",
        "high_risk_destination_share", "n_counterparties", "alerts_raised",
        "compliance_recommended_exit_or_sar", "management_overrides",
        "introducer_assurance_used", "sar_filed", "days_alert_to_sar",
        "source_of_funds_verified", "risk_score", "risk_level",
        "escalate_to_finma", "is_suspicious", "scenario",
    ],
}

# Numeric columns to coerce per table.
_NUMERIC: dict[str, list[str]] = {
    "entities": ["declared_income_usd", "expected_monthly_volume_usd"],
    "network_edges": ["total_usd", "txn_count"],
    "transactions": ["amount_usd"],
    "pep_quarterly_report": [
        "inflow_usd", "outflow_usd", "cash_usd", "pass_through_ratio",
        "volume_vs_expected", "high_risk_destination_share", "n_counterparties",
        "alerts_raised", "compliance_recommended_exit_or_sar",
        "management_overrides", "introducer_assurance_used", "sar_filed",
        "days_alert_to_sar", "risk_score",
    ],
}


class DataValidationError(Exception):
    """Raised when a dataset is missing columns or has malformed values."""


@dataclass
class Datasets:
    """The four loaded, validated frames."""

    entities: pd.DataFrame
    network_edges: pd.DataFrame
    transactions: pd.DataFrame
    pep_quarterly_report: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "entities": self.entities,
            "network_edges": self.network_edges,
            "transactions": self.transactions,
            "pep_quarterly_report": self.pep_quarterly_report,
        }


def _validate_and_coerce(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Validate required columns and coerce numerics."""
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
    if missing:
        raise DataValidationError(
            f"{name} is missing required column(s): {', '.join(missing)}"
        )

    # Coerce numerics; invalid values become NaN rather than crashing, but a
    # column that is entirely non-numeric is a hard error (malformed data).
    for col in _NUMERIC.get(name, []):
        coerced = pd.to_numeric(df[col], errors="coerce")
        if df[col].notna().any() and coerced.notna().sum() == 0:
            raise DataValidationError(
                f"{name} column '{col}' contains no numeric values"
            )
        df[col] = coerced

    return df


def _read_one_csv(name: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / f"{name}.csv"
    if not path.exists():
        raise DataValidationError(f"Missing data file: {path}")
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas raises many parse types
        raise DataValidationError(f"Could not parse {path}: {exc}") from exc

    return _validate_and_coerce(df, name)


def _normalise_bool_text(series: pd.Series) -> pd.Series:
    """Normalise Yes/No-style text to a consistent capitalised form."""
    return series.astype("string").str.strip().str.capitalize()


def load_all(
    data_dir: Path | str = DATA_DIR,
    use_db: bool = True,
    db_path: Path | str | None = None,
) -> Datasets:
    """Load and validate all four tables.

    If ``use_db=True``, reads from SQLite (auto-seeded from ``dataset2/`` on first run).
    Otherwise reads directly from CSVs in ``data_dir``.

    Raises :class:`DataValidationError` with a readable message if any table is
    missing, missing a required column, or has a malformed numeric column.
    """
    data_dir = Path(data_dir)

    if use_db:
        try:
            entities = _validate_and_coerce(DBM.load_table("entities", db_path=db_path), "entities")
            edges = _validate_and_coerce(DBM.load_table("network_edges", db_path=db_path), "network_edges")
            txns = _validate_and_coerce(DBM.load_table("transactions", db_path=db_path), "transactions")
            report = _validate_and_coerce(DBM.load_table("pep_quarterly_report", db_path=db_path), "pep_quarterly_report")
        except Exception:
            # Fallback to CSV if DB access fails
            entities = _read_one_csv("entities", data_dir)
            edges = _read_one_csv("network_edges", data_dir)
            txns = _read_one_csv("transactions", data_dir)
            report = _read_one_csv("pep_quarterly_report", data_dir)
    else:
        entities = _read_one_csv("entities", data_dir)
        edges = _read_one_csv("network_edges", data_dir)
        txns = _read_one_csv("transactions", data_dir)
        report = _read_one_csv("pep_quarterly_report", data_dir)

    # Parse transaction dates (Requirement 8.1 drill-down over time).
    txns["date"] = pd.to_datetime(txns["date"], errors="coerce")

    # Normalise common Yes/No text columns so downstream comparisons are robust.
    for col in ("flagged_as_pep_by_bank", "source_of_funds_verified"):
        entities[col] = _normalise_bool_text(entities[col])
    report["flagged_as_pep_by_bank"] = _normalise_bool_text(
        report["flagged_as_pep_by_bank"]
    )
    report["source_of_funds_verified"] = _normalise_bool_text(
        report["source_of_funds_verified"]
    )
    edges["known_to_bank"] = _normalise_bool_text(edges["known_to_bank"])

    return Datasets(entities, edges, txns, report)
