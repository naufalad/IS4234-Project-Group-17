# Design — FINMA PEP Supervisory Analytics & Automated Reporting

## Overview

A regulator-side (FINMA) analytics layer that ingests HSBC's PEP-scoped
submissions, re-derives risk independently of the bank's own alerts, runs
network analytics to surface what the bank missed, and auto-escalates
threshold breaches. Delivered as a Streamlit multi-page app over `dataset2/`,
kept fully separate from the existing data-assurance dashboard (`app.py`).

Design principles:

- **Independence.** Risk and escalation never read the answer-key columns
  (`is_suspicious`, `scenario`, `typology`). Those feed validation only.
- **Transparency.** The risk score is a small, inspectable rule set driven by an
  editable config; every score shows its contributing factors.
- **Separation.** New code lives in `pep_analytics/` + `pep_app.py`; existing
  files are untouched.

## Architecture

```
dataset2/*.csv
      │  (load + validate)
      ▼
┌─────────────────────┐
│  pep_analytics      │   pure-Python / pandas / networkx, no Streamlit
│  ├─ data_loader.py  │   load, join, validate, cache
│  ├─ config.py       │   adjustable thresholds & weights (dataclass)
│  ├─ scoring.py      │   transparent 0–100 risk score + factor breakdown
│  ├─ graph.py        │   build graph, clusters, pass-through, hidden links
│  ├─ exceptions.py   │   SoF gaps, overrides, introducer reliance
│  ├─ escalation.py   │   escalation records + export
│  ├─ review.py       │   independent KYC-review worklist + refresh intervals
│  └─ validation.py   │   precision/recall vs answer key
└─────────────────────┘
      │  (presentation only)
      ▼
┌─────────────────────┐
│  pep_app.py         │   Streamlit entry
│  pages/             │
│  ├─ 1_Overview.py   │
│  ├─ 2_Watchlist.py  │
│  ├─ 3_Network.py    │
│  ├─ 4_Governance.py │   exceptions + overrides
│  ├─ 5_Review.py     │   KYC review worklist
│  ├─ 6_Drilldown.py  │
│  └─ 7_Validation.py │
└─────────────────────┘
```

The analytics package is UI-agnostic so it is unit-testable and reusable (e.g.
from the notebook or a batch export job).

## Components and Interfaces

### `config.py`
A frozen dataclass holding tunable parameters, with sensible defaults matching
`dataset2/README.md`:

```python
@dataclass
class RiskConfig:
    pass_through_ratio_min: float = 0.8
    pass_through_inflow_min: float = 100_000
    volume_vs_expected_min: float = 5.0
    high_risk_dest_share_min: float = 0.5
    cash_min: float = 50_000
    sof_materiality_min: float = 100_000       # Req 5.1
    weights: dict = default_weights()          # 25/20/15/15/10/15/15
    escalate_at: int = 60                       # Req 6.1
    max_days_alert_to_sar: int = 90             # Req 6.2
    kyc_review_interval_quarters: int = 4       # Req 7.3
```
The UI exposes these via sidebar controls and passes an overridden config into
scoring/escalation so changes recompute consistently (Req 3.4–3.5).

### `data_loader.py`
- `load_all() -> Datasets` returns the four frames, parsed and type-coerced
  (`date` as datetime, numeric columns as float/int, booleans normalised).
- Validates presence of required columns per Req 2.3 and raises a readable
  `DataValidationError` listing what is missing/malformed.
- `@st.cache_data`-friendly: the heavy load is a plain function; the Streamlit
  layer wraps it with caching.

### `scoring.py`
- `score_report(df, cfg) -> df` adds `risk_score`, `risk_level`,
  `escalate_to_finma`, and a `score_factors` column (list of
  `(factor, points)`), computed only from input signals (Req 3.1–3.3, 3.6).
- A recomputation check verifies the derived score matches the dataset's
  provided `risk_score` under default config (sanity test, not a runtime dep).

### `graph.py`
- `build_graph(entities, edges, cfg) -> networkx.DiGraph` with node attributes
  (`pep_category`, `flagged_as_pep_by_bank`, `swiss_bank`, `risk_score`) and
  edge attributes (`edge_type`, `known_to_bank`, `total_usd`, `is_hidden`).
- `communities(G)` — community detection (greedy modularity / label
  propagation from `networkx`) → cluster ids (Req 4.1).
- `pass_through_entities(report, cfg)` — entities with near-1 ratios and
  material inflow (Req 4.2).
- `blind_spots(entities)` — PEP-linked AND `flagged_as_pep_by_bank = No`
  (Req 4.3).
- `rank_clusters(...)` — composite exposure = aggregate flow × hidden-link
  presence × max risk score (Req 4.4–4.5).
- `plotly_figure(G, ...)` — layout + traces; dashed/red styling for
  `is_hidden` edges, node colour by `pep_category` (Req 1.2–1.4).

### `exceptions.py`
- `sof_exceptions(report, cfg)` (Req 5.1), `override_exceptions(report)`
  (Req 5.2), `introducer_reliance(report)` (Req 5.3),
  `aggregate_by_bank_quarter(...)` (Req 5.4).

### `escalation.py`
- `build_escalations(scored, cfg) -> df` — one record per breaching
  client-quarter with entity, quarter, bank, score, factors, trigger reason;
  includes the SAR-delay trigger (Req 6.1–6.3). No manual gate (Req 6.4).
- `to_csv(...)` export (Req 6.5).

### `review.py`
- `review_worklist(entities, edges, scored, cfg)` — PEPs + close associates +
  PEP-owned companies, seeded by blind spots and hidden edges, prioritised by
  risk/exposure, with a `due_for_refresh` flag from the interval (Req 7).

### `validation.py`
- `evaluate(scored, escalations, keys)` — precision/recall of escalations vs
  `is_suspicious`; count of bank-missed cases caught (Req 9). Imports the
  answer-key columns here and nowhere else.

## Data Models

**ScoredReport** = `pep_quarterly_report` columns + `risk_score`, `risk_level`,
`escalate_to_finma`, `score_factors`.

**EscalationRecord**: `entity_id, name, quarter, swiss_bank, risk_score,
trigger_reason, factors, pep_category, flagged_as_pep_by_bank`.

**GraphNode**: `id, name, pep_category, flagged_as_pep_by_bank, swiss_bank,
risk_score, cluster_id`.
**GraphEdge**: `source, target, edge_type, known_to_bank, total_usd, is_hidden`.

## UI pages (mapping to README's suggested pages)

1. **Overview** — KPIs: PEP clients, high-risk count, total PEP inflows,
   override count, avg days-to-SAR; risk level by bank.
2. **Watchlist** — High-risk client-quarters sorted by score, with factor
   breakdown on expand.
3. **Network** — graph (Req 1), cluster ranking panel (Req 4).
4. **Governance** — SoF gaps, overrides, introducer reliance by bank/quarter
   (Req 5).
5. **Review** — independent KYC-review worklist (Req 7).
6. **Drill-down** — one entity: transactions over time, counterparties,
   subgraph, risk history (Req 8).
7. **Validation** — precision/recall and bank-missed-caught counts (Req 9).

## Error Handling

- Missing/malformed input → `DataValidationError` surfaced in the UI with the
  offending column(s), never a silent failure (Req 2.3).
- Division-safe ratios (guard zero inflow) in scoring and pass-through logic.
- Empty filter results render an explicit "no rows" state rather than erroring.
- Config overrides validated (non-negative weights, 0–100 escalation threshold).

## Testing Strategy

- **Unit:** scoring rules (each factor fires correctly; cap at 100; level
  mapping); pass-through and blind-spot detection; escalation triggers;
  config-override recomputation.
- **Regression/sanity:** recomputed `risk_score` under default config matches the
  dataset's provided `risk_score`.
- **Validation harness:** `validation.py` reports precision/recall against the
  answer key (demonstrates value over the bank's own flagging).
- Tests added only as the implementation lands, not pre-emptively.

## Dependencies

Add to `requirements.txt` (keep existing `streamlit`, `pandas`, `plotly`):
`networkx` (graph + community detection). No change to existing files.

## Technical decisions

- **Streamlit multi-page** mirrors the README's suggested dashboard pages and
  keeps the regulator app separate from `app.py`.
- **networkx** chosen over heavier graph DBs: dataset is small (≈720 nodes,
  ≈2.7k edges), in-memory analysis is instant and dependency-light.
- **Config-driven scoring** satisfies the "transparent, adjustable" requirement
  and keeps escalation defensible.
- **Answer key isolated** to `validation.py` to structurally guarantee it never
  leaks into scoring or escalation.
