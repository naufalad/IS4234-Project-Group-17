# Requirements — FINMA PEP Supervisory Analytics & Automated Reporting

## Introduction

HSBC is under investigation in Lebanon for anti-money-laundering (AML) failures
concerning politically exposed person (PEP) accounts. On the Swiss side, the
supervisory response (FINMA) is **not** to trust the bank's own flagging but to
run **independent supervisory analytics** on data the bank is required to submit.

This feature builds a regulator-side analytics and automated-reporting layer that:

- requires HSBC to submit structured, PEP-scoped data (profiles, relationships,
  money flows, and a quarterly compliance report);
- re-derives risk independently of the bank's own alerts;
- runs network analysis to surface clusters, hidden links, and PEP blind spots
  the bank's rule-based monitoring missed;
- escalates to FINMA automatically when a risk threshold is breached;
- supports periodic independent KYC review of PEP accounts and their close
  associates (Jyske-bank reference model);
- is grounded in network-analytics logic for AML
  (McKinsey — "Network analytics and the fight against money laundering").

### Data (synthetic, `dataset2/`)

| File | Rows | Role |
|---|---|---|
| `entities.csv` | 720 | Network nodes + client profile cards |
| `network_edges.csv` | 2,658 | Network edges (relationships + money flows) |
| `transactions.csv` | 7,354 | Drill-down, time and flow charts |
| `pep_quarterly_report.csv` | 2,084 | Main structured report — one row per PEP-linked client per quarter |

All tables join on `entity_id` (= `source_id` / `target_id` / `from_id` / `to_id`).

> **Answer key, not input.** `is_suspicious`, `scenario`, and `typology` are the
> ground-truth labels. They are used only to measure detection quality
> (precision/recall). They must never be inputs to the risk score, graph
> analytics, or escalation logic.

---

## Requirements

### Requirement 1 — PEP network graph (regulator-side)

**User story:** As a FINMA supervisor, I want a network graph scoped to PEPs and
their connected entities, so that I can see relationships and money flows,
including links the bank never reported.

#### Acceptance Criteria

1. WHEN the supervisor opens the Network view THEN the system SHALL render a
   directed graph of PEP-linked entities built from `entities.csv` (nodes) and
   `network_edges.csv` (edges).
2. WHERE an entity is PEP-linked, the system SHALL colour the node by
   `pep_category` (PEP, PEP family, PEP close associate, PEP-owned company).
3. WHEN an edge has `known_to_bank = No` THEN the system SHALL render it with a
   visually distinct style (e.g. dashed/red) to mark links found only by the
   regulator or independent review.
4. THE system SHALL style or label edges by `edge_type` (Family, Owns, Director,
   Nominee director, Close associate, Money transfer, etc.).
5. WHEN the supervisor selects a node THEN the system SHALL expose that entity's
   immediate subgraph and allow navigation to its client drill-down.

### Requirement 2 — Structured quarterly PEP report ingestion

**User story:** As a FINMA supervisor, I want the mandated quarterly PEP report
ingested into a reviewable table, so that I have one row per PEP-linked client
per quarter with the governance and flow signals needed for supervision.

#### Acceptance Criteria

1. WHEN the quarterly report is loaded THEN the system SHALL present one row per
   `(quarter, entity_id)` from `pep_quarterly_report.csv`.
2. THE system SHALL surface, per row: inflow/outflow/cash, `pass_through_ratio`,
   `volume_vs_expected`, `high_risk_destination_share`, `n_counterparties`,
   `alerts_raised`, `compliance_recommended_exit_or_sar`, `management_overrides`,
   `introducer_assurance_used`, `sar_filed`, `days_alert_to_sar`,
   `source_of_funds_verified`, and `flagged_as_pep_by_bank`.
3. IF a required column is missing or a value is malformed THEN the system SHALL
   report a clear ingestion/validation error rather than failing silently.
4. THE system SHALL allow filtering by quarter, Swiss bank, and PEP category.

### Requirement 3 — Transparent, adjustable risk scoring

**User story:** As a FINMA supervisor, I want a transparent 0–100 risk score I
can inspect and tune, so that escalation decisions are explainable and
defensible.

#### Acceptance Criteria

1. THE system SHALL recompute a 0–100 risk score per client-quarter using these
   rules: pass_through_ratio ≥ 0.8 AND inflow > $100k (25); volume_vs_expected
   > 5 (20); high_risk_destination_share > 0.5 (15); PEP-linked but not flagged
   by bank (15); source of funds not verified (10); management override this
   quarter (15); cash deposits > $50k (15). Score SHALL be capped at 100.
2. THE system SHALL map score to risk level: Low < 30, Medium 30–59, High ≥ 60.
3. THE risk score SHALL NOT use `is_suspicious`, `scenario`, or `typology` as
   inputs.
4. WHERE thresholds and point weights are defined, the system SHALL load them
   from an adjustable configuration so a supervisor can tune them without code
   changes.
5. WHEN a supervisor changes a threshold THEN the system SHALL recompute scores,
   risk levels, and escalation flags consistently.
6. THE system SHALL show the contributing factors (score breakdown) for any
   client-quarter.

### Requirement 4 — Network analytics to surface what the bank missed

**User story:** As a FINMA supervisor, I want network analytics across the
submitted data, so that I can spot clusters, pass-through chains, and nominee
structures that HSBC's rule-based monitoring missed.

#### Acceptance Criteria

1. THE system SHALL detect connected clusters/communities within the PEP network.
2. THE system SHALL identify pass-through chains (money entering and leaving an
   entity at a near-1 ratio) and highlight entities on such chains.
3. THE system SHALL flag every entity that is PEP-linked but has
   `flagged_as_pep_by_bank = No` (bank blind spots).
4. THE system SHALL prioritise clusters that combine `known_to_bank = No` edges
   with suspicious money flows.
5. WHEN analytics complete THEN the system SHALL rank clusters/entities by a
   composite exposure measure (e.g. aggregate flow × hidden-link presence ×
   risk score).

### Requirement 5 — Source-of-funds and compliance-override exceptions

**User story:** As a FINMA supervisor, I want dedicated exception reporting on
source-of-funds gaps and management overrides, so that governance failures at
the centre of the case are visible.

#### Acceptance Criteria

1. THE system SHALL list PEP client-quarters WHERE `source_of_funds_verified` is
   not "Yes" AND inflow exceeds a configurable materiality threshold.
2. THE system SHALL list client-quarters WHERE `management_overrides = 1` AND
   `compliance_recommended_exit_or_sar = 1` (override against compliance advice).
3. THE system SHALL report reliance on `introducer_assurance_used`.
4. THE system SHALL aggregate these exceptions by Swiss bank and by quarter to
   expose trends over time.

### Requirement 6 — Mandatory escalation on threshold breach

**User story:** As a FINMA supervisor, I want escalation to FINMA to happen
automatically when thresholds are breached, so that no high-risk case depends on
a manual gate.

#### Acceptance Criteria

1. WHEN a client-quarter risk score ≥ the escalation threshold (default 60) THEN
   the system SHALL set `escalate_to_finma = Yes` and generate an escalation
   record automatically.
2. THE system SHALL also treat an excessive SAR delay (`days_alert_to_sar`
   beyond a configurable limit) as an escalation trigger.
3. THE escalation record SHALL include entity, quarter, Swiss bank, score,
   contributing factors, and trigger reason.
4. THE system SHALL NOT require manual approval before producing the escalation
   record.
5. THE system SHALL make the full set of escalation records exportable.

### Requirement 7 — Independent KYC review support

**User story:** As a FINMA supervisor, I want a prioritised worklist for
independent KYC review of PEP accounts and close associates, so that reviews and
KYC refreshes happen at set intervals (Jyske-bank reference).

#### Acceptance Criteria

1. THE system SHALL produce a worklist of PEP accounts recommended for
   independent KYC review, seeded by blind spots (Req 4.3) and hidden edges
   (Req 1.3).
2. THE worklist SHALL include PEPs and their close associates and PEP-owned
   companies.
3. THE system SHALL support a configurable review interval and flag accounts due
   for KYC refresh based on last-review timing.
4. THE worklist SHALL be prioritised by risk score and exposure.

### Requirement 8 — Client drill-down

**User story:** As a FINMA supervisor, I want to drill into a single entity, so
that I can inspect its transactions over time, counterparties, and subgraph.

#### Acceptance Criteria

1. WHEN the supervisor selects an entity THEN the system SHALL show its
   transactions from `transactions.csv` over time.
2. THE system SHALL show the entity's counterparties and per-counterparty flow.
3. THE system SHALL show the entity's immediate network subgraph.
4. THE drill-down SHALL show the entity's quarterly risk history.

### Requirement 9 — Detection quality validation

**User story:** As a FINMA supervisor (and as the project team), I want to
measure how well the analytics detect known-bad cases, so that the solution's
value over the bank's own flagging is demonstrable.

#### Acceptance Criteria

1. THE system SHALL compare escalation/flag outputs against the `is_suspicious`,
   `scenario`, and `typology` answer keys to compute precision and recall.
2. THE system SHALL report how many suspicious cases the bank missed
   (`bank_raised_alert = No` / `flagged_as_pep_by_bank = No`) that the analytics
   caught.
3. THE answer-key columns SHALL be used only for this validation step.

### Requirement 10 — Separation from existing dashboard

**User story:** As a project team member, I want this PEP analytics solution to
be separate from the existing data-assurance dashboard, so that neither breaks
the other.

#### Acceptance Criteria

1. THE new solution SHALL live in its own module/app and read from `dataset2/`.
2. THE system SHALL NOT modify or depend on the existing `app.py` /
   `reconcile.py` (which operate on `dataset/`).
3. NEW dependencies SHALL be added to `requirements.txt` without removing
   existing ones.
