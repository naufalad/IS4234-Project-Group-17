# IS4234-Group-Project

## FINMA PEP Supervisory Analytics

A regulator-side (FINMA) analytics and automated-reporting layer over
synthetic, bank-submitted PEP data. It ingests the banks' PEP-scoped
submissions, re-derives risk **independently** of the bank's own alerts, runs
network analytics to surface clusters and hidden links the bank missed, and
auto-escalates threshold breaches into cases that FINMA officers can be
assigned to.

### Data

- **`dataset1/`**: the baseline used to seed the app's SQLite database
  (`entities_flat.csv`, `network_edges_flat.csv`, `transactions_flat.csv`,
  `pep_quarterly_report_flat.csv`). The database is seeded only when its tables
  are empty; use the reset button on the Home page to wipe it and re-seed from
  `dataset1/`.
- **`dataset2/`**: an alternative version of the same four tables. Its
  `README.md` is the data dictionary and documents the risk-score rules both
  datasets follow.
- New data can be added at runtime through the batch CSV/JSON upload on the Home
  page.

### Run

```bash
pip install -r requirements.txt
streamlit run pep_app.py
```

### Pages

The app has 7 pages in its top navigation (defined in `pep_app.py`):

| Page | What it shows |
|---|---|
| Home | Live KPIs (refreshed from the database every 2s), batch CSV/JSON upload with sample downloads, database reset, and links to each page |
| Overview | Portfolio KPIs, risk level by Swiss bank, bank alerting vs suspicion, cases the bank missed, and the independent KYC-review worklist (CSV export) |
| Watchlist | Client-quarters filterable by quarter, bank, PEP category and risk level, with a transparent score breakdown |
| Network | PEP network graph (hidden links dashed-red) filterable by entity type or single entity, plus hidden edges, bank blind spots and pass-through client-quarters |
| Governance | Exception counts by bank over time, source-of-funds gaps, management overrides and introducer reliance |
| Drilldown | One entity: transactions over time, counterparties, quarterly risk history and network subgraph |
| Case Management | Drag-and-drop board for assigning critical cases to FINMA officers, managing assignments and tracking case status |

> `pages/5_Review.py` and `pages/7_Validation.py` are still in the repo but are
> not registered in the navigation; the KYC-review worklist now lives on the
> Overview page.

### Design notes

- **Transparent, adjustable risk score.** Implements the exact 0–100 risk table
  from `dataset2/README.md`; all thresholds and weights are tunable from the
  sidebar (`pep_analytics/config.py`). Under default config the recomputed
  `risk_score` reproduces the dataset's own `risk_score` for all rows of
  `dataset1/`.
- **Live database.** Pages read from SQLite (`pep_analytics/db.py`) rather
  than the CSVs directly, so batch uploads, case assignments and resets are
  reflected across the app.
- **Answer-key isolation.** `is_suspicious`, `scenario` and `typology` are read
  only by `pep_analytics/validation.py`. They never feed
  scoring, the graph, or escalation.

### Code layout

```
pep_app.py              Streamlit entry, Home page and top navigation
pages/                  One file per dashboard page
dataset1/               Baseline CSVs used to seed the database
dataset2/               Alternative dataset + data dictionary (README.md)
pep_analytics/
  config.py             RiskConfig (adjustable thresholds/weights)
  ui.py                 shared Streamlit helpers (data loading, config sidebar)
  data_loader.py        load + validate the four tables from SQLite (CSV fallback)
  db.py                 SQLite persistence, baseline seeder, cases & officers
  batch.py              sample CSV/JSON batch generation + upload normalisation
  scoring.py            transparent 0-100 risk score + factor breakdown
  graph.py              graph build, clusters, pass-through, hidden links, Plotly
  exceptions.py         SoF / override / introducer exception reports
  escalation.py         automated escalation records + CSV export
  review.py             independent KYC-review worklist
  validation.py         detection checks vs the answer key
  entity_resolution.py  fuzzy name matching to detect PEP aliases
  dossier.py            regulatory SAR dossier generator (MROS / FINMA report)
  generator.py          scenario-aware typology presets (Forry/Lebanon case)
  case_board.py         drag-and-drop case assignment component
  case_board_frontend/  HTML/JS frontend for the case board
tests/                  pytest unit tests
```

### Tests

```bash
pytest
```
