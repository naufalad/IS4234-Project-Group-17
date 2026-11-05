# FINMA PEP Supervision — simplified synthetic dataset

Four tables. All names are fictional; the pattern mirrors the HSBC Geneva / Forry case (2002–2016).
`is_suspicious` and `scenario` are the answer key — use them to check results, not as inputs.

| File | Rows | Use it for |
|---|---|---|
| entities.csv | 720 | Network **nodes** + client profile cards |
| network_edges.csv | 2,658 | Network **edges** (relationships + money flows) |
| transactions.csv | 7,354 | Drill-down, time charts, flow charts |
| pep_quarterly_report.csv | 2,084 | **Main dashboard table** — one row per PEP-linked client per quarter |

Join everything on `entity_id` (= `source_id` / `target_id` / `from_id` / `to_id`).

## 1. entities.csv
| Column | Meaning |
|---|---|
| entity_id, name | ID and name |
| entity_type | Person / Company / Government body |
| country | Country code (VG = BVI, PA = Panama) |
| pep_category | Not PEP / PEP / PEP family / PEP close associate / PEP-owned company |
| linked_pep_id, linked_pep_name, pep_role | Which PEP they connect to; public role for PEPs |
| flagged_as_pep_by_bank | Did the bank tag them as PEP-related? "No" on a PEP-linked entity = bank blind spot |
| swiss_bank | Swiss bank holding their account, or "None (foreign counterparty)" |
| offshore_jurisdiction | Yes for BVI, Panama, Cyprus |
| declared_income_usd, expected_monthly_volume_usd | What the client declared at onboarding |
| source_of_funds_verified | Yes / No / Unknown |
| bank_risk_rating | Bank's own rating |
| is_suspicious, scenario | Answer key |

## 2. network_edges.csv
| Column | Meaning |
|---|---|
| source_id/name → target_id/name | Directed link |
| edge_type | Family, Owns, Director, Nominee director, Close associate, Introduced client, Official role at, Contract with, Employed by, **Money transfer** |
| detail | Finer type (e.g. Family Sibling) |
| total_usd, txn_count | Money transfer edges only |
| known_to_bank | "No" = hidden link found only by regulator / independent review |
| found_via | Bank KYC, Corporate Registry, PEP Database, Independent Review, Bank transaction report |
| is_suspicious | Answer key |

## 3. transactions.csv
All transactions touching a PEP network, plus 3,000 normal ones and a sample of the decoy trader.
| Column | Meaning |
|---|---|
| txn_id, date, quarter | When |
| from_id/name/country → to_id/name/country | Who to whom |
| amount_usd | Value in USD |
| type | International wire, Domestic wire, Internal transfer, Cash deposit, Securities purchase |
| purpose | Payment reference |
| swiss_bank | Reporting Swiss bank |
| bank_raised_alert | Did the bank's system alert? |
| is_suspicious, typology | Answer key (e.g. PEP_PASS_THROUGH, FEE_DIVERSION, KICKBACK, STRUCTURING, Normal) |

## 4. pep_quarterly_report.csv — the structured report FINMA would require
| Column | Meaning |
|---|---|
| quarter, entity_id, name, pep_category, linked_pep_name, swiss_bank, flagged_as_pep_by_bank | Who / when |
| inflow_usd, outflow_usd, cash_usd | Money in, out, cash deposits that quarter |
| pass_through_ratio | outflow ÷ inflow (≈1 = money just passes through) |
| volume_vs_expected | inflow ÷ (expected monthly volume × 3) |
| high_risk_destination_share | Share of outflows to offshore / high-risk countries |
| n_counterparties | Distinct receivers |
| alerts_raised | Bank alerts that quarter |
| compliance_recommended_exit_or_sar | Compliance said exit or report |
| management_overrides | Management overruled compliance |
| introducer_assurance_used | Decision relied on an introducer vouching |
| sar_filed, days_alert_to_sar | Reporting to the authorities and its delay |
| source_of_funds_verified | From KYC |
| risk_score (0–100), risk_level, escalate_to_finma | Regulator score (below) |
| is_suspicious, scenario | Answer key |

### Risk score (transparent, adjustable)
| Condition | Points | Notes
|---|---|---|
| pass_through_ratio ≥ 0.8 and inflow > $100k | 10 
| volume_vs_expected > 5 | 10 
| high_risk_destination_share > 0.5 | 10 
| PEP-linked but not flagged by bank | 20 
| Source of funds not verified | 20 
| Management override this quarter | 15 
| Cash deposits > $50k | 15 


Capped at 100. Low < 30, Medium 30–59, High ≥ 60 → `escalate_to_finma = Yes`.

## dashboard pages
1. **Overview** — KPIs: PEP clients, high-risk count, total PEP inflows, overrides, avg days to SAR; risk level by bank.
2. **Watchlist** — table of High-risk client-quarters, sorted by score.
3. **Bank governance** — overrides, introducer reliance and SAR delay by bank over time.
4. **Network** — graph from entities + network_edges; colour by pep_category, dashed for `known_to_bank = No`.
5. **Client drill-down** — transactions for one entity over time.
