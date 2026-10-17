# Implementation Plan — FINMA PEP Supervisory Analytics

- [ ] 1. Scaffold the analytics package and app shell
  - Create `pep_analytics/` package and `pep_app.py` Streamlit entry; add
    `networkx` to `requirements.txt` without removing existing deps.
  - Confirm the app runs and reads from `dataset2/` without touching `app.py`.
  - _Requirements: 10.1, 10.2, 10.3_

- [ ] 2. Data loading and validation
  - [ ] 2.1 Implement `data_loader.load_all()` to load, join-ready, and
    type-coerce the four `dataset2/` tables (dates, numerics, booleans).
    - _Requirements: 2.1, 2.2_
  - [ ] 2.2 Add column/value validation raising a readable `DataValidationError`
    on missing or malformed data.
    - _Requirements: 2.3_

- [ ] 3. Config and transparent risk scoring
  - [ ] 3.1 Implement `config.RiskConfig` dataclass with README defaults
    (weights, thresholds, escalation level, review interval).
    - _Requirements: 3.4_
  - [ ] 3.2 Implement `scoring.score_report()` producing `risk_score`,
    `risk_level`, `escalate_to_finma`, and a per-row factor breakdown, using
    only input signals (never the answer key).
    - _Requirements: 3.1, 3.2, 3.3, 3.6_
  - [ ] 3.3 Add a sanity check that recomputed scores match the dataset's
    `risk_score` under default config.
    - _Requirements: 3.1_
  - [ ] 3.4 Wire sidebar controls so config overrides recompute scores, levels,
    and escalation flags consistently.
    - _Requirements: 3.4, 3.5_

- [ ] 4. Overview and Watchlist pages
  - [ ] 4.1 Overview page: KPIs (PEP clients, high-risk count, total PEP
    inflows, override count, avg days-to-SAR) and risk level by bank.
    - _Requirements: 2.4, 3.2_
  - [ ] 4.2 Watchlist page: High-risk client-quarters sorted by score with
    expandable factor breakdown; filters by quarter, bank, PEP category.
    - _Requirements: 2.4, 3.6_

- [ ] 5. Network graph and analytics
  - [ ] 5.1 Implement `graph.build_graph()` with node and edge attributes
    (incl. `is_hidden` from `known_to_bank = No`).
    - _Requirements: 1.1, 1.2, 1.4_
  - [ ] 5.2 Implement `graph.plotly_figure()` — node colour by `pep_category`,
    dashed/red styling for hidden edges, node selection to subgraph.
    - _Requirements: 1.2, 1.3, 1.5_
  - [ ] 5.3 Implement cluster/community detection, pass-through detection, and
    blind-spot detection.
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ] 5.4 Implement composite cluster ranking (flow × hidden-link × risk) and
    render the ranked panel on the Network page.
    - _Requirements: 4.4, 4.5_

- [ ] 6. Governance / exceptions page
  - [ ] 6.1 Implement source-of-funds, override-against-compliance, and
    introducer-reliance exception functions.
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ] 6.2 Render exceptions aggregated by Swiss bank and quarter to show
    trends over time.
    - _Requirements: 5.4_

- [ ] 7. Automated escalation
  - [ ] 7.1 Implement `escalation.build_escalations()` with score and SAR-delay
    triggers, full record fields, and no manual gate.
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [ ] 7.2 Add CSV export of escalation records and surface it in the UI.
    - _Requirements: 6.5_

- [ ] 8. Independent KYC review worklist
  - Implement `review.review_worklist()` covering PEPs, close associates, and
    PEP-owned companies; seeded by blind spots and hidden edges; prioritised by
    risk/exposure; with a configurable refresh-interval `due_for_refresh` flag.
    Render on the Review page.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Client drill-down page
  - Implement the Drill-down page: entity transactions over time, counterparties
    and per-counterparty flow, immediate subgraph, and quarterly risk history.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 10. Detection-quality validation
  - Implement `validation.evaluate()` computing precision/recall of escalations
    vs the answer key and counting bank-missed cases caught; render on the
    Validation page. Answer-key columns used only here.
  - _Requirements: 9.1, 9.2, 9.3_

- [ ] 11. Tests and wiring
  - Add unit tests for scoring factors/cap/levels, pass-through and blind-spot
    detection, escalation triggers, and config-override recomputation; ensure
    all pages load end-to-end from `dataset2/`.
  - _Requirements: 3.1, 3.5, 4.2, 4.3, 6.1_
