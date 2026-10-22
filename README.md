# IS4234-Group-Project

## FINMA PEP Supervisory Analytics

A regulator-side (FINMA) analytics and automated-reporting layer over the
synthetic PEP dataset in `dataset2/`. It ingests the bank's PEP-scoped
submissions, re-derives risk **independently** of the bank's own alerts, runs
network analytics to surface clusters and hidden links the bank missed, and
auto-escalates threshold breaches.

> This app is separate from the existing data-assurance dashboard (`app.py` /
> `reconcile.py`, which operate on `dataset/`). It touches neither.

### Run

```bash
pip install -r requirements.txt
streamlit run pep_app.py
```

### Pages

| Page | What it shows |
|---|---|
| Overview | Portfolio KPIs and risk level by Swiss bank |
| Watchlist | High-risk client-quarters with a transparent score breakdown |
| Network | PEP network graph (hidden links dashed-red) + cluster exposure ranking, blind spots, pass-through |
| Governance | Source-of-funds gaps, management overrides, introducer reliance, and auto-generated escalation records (CSV export) |
| Review | Independent KYC-review worklist (Jyske-bank reference), prioritised, with refresh-due flags |
| Drilldown | One entity: transactions over time, counterparties, subgraph, quarterly risk history |
| Validation | Detection quality (precision/recall) vs the answer key |
| Live CMS | Case Management gateway: single-entry submission, Lebanon case typology presets & interval streaming simulator |

### Design notes

- **Transparent, adjustable risk score.** Implements the exact 0–100 risk table
  from `dataset2/README.md`; all thresholds and weights are tunable from the
  sidebar (`pep_analytics/config.py`). Under default config the recomputed
  `risk_score` reproduces the dataset's own `risk_score` for all rows.
- **Answer-key isolation.** `is_suspicious`, `scenario` and `typology` are read
  only by `pep_analytics/validation.py` (the Validation page). They never feed
  scoring, the graph, or escalation.

### Code layout

```
pep_app.py              Streamlit entry + shared config sidebar
pages/                  One file per dashboard page
pep_analytics/
  config.py             RiskConfig (adjustable thresholds/weights)
  data_loader.py        load + validate dataset2/ (DataValidationError)
  scoring.py            transparent 0-100 risk score + factor breakdown
  graph.py              graph build, clusters, pass-through, hidden links, Plotly
  exceptions.py         SoF / override / introducer exception reports
  escalation.py         automated escalation records + CSV export
  review.py             independent KYC-review worklist
  validation.py         precision/recall vs answer key
  db.py                 SQLite persistence, baseline seeder & audit logging
  generator.py          scenario-aware typology presets (Forry/Lebanon case)
tests/                  pytest unit tests
```

### Tests

```bash
pytest
```
