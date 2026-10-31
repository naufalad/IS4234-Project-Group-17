"""Automated Regulatory SAR Dossier Generator (MROS / FINMA Report).

Synthesizes structured case data, entity profile, network relationships,
governance exceptions, and financial flows into a formal regulatory dossier
ready for submission to MROS (Money Laundering Reporting Office Switzerland).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def generate_sar_dossier(
    case: dict[str, Any],
    entity: dict[str, Any],
    report: dict[str, Any] | None = None,
    edges: list[dict[str, Any]] | None = None,
    transactions: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a formal, structured MROS/FINMA investigative dossier in Markdown."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    case_id = case.get("case_id", "CASE-UNKNOWN")
    entity_id = entity.get("entity_id", "ENT-UNKNOWN")
    entity_name = entity.get("name", "Unknown Entity")
    bank = entity.get("swiss_bank", "Unknown Bank")
    pep_cat = entity.get("pep_category", "Unknown")
    country = entity.get("country", "Unknown")
    risk_score = case.get("risk_score", 0.0)
    status = case.get("status", "NEW_ALERT")
    supervisor = case.get("assigned_supervisor", "Unassigned")
    investigation_notes = case.get("investigation_notes") or "Initial triage completed. Awaiting formal bank response."
    override_justification = case.get("override_justification") or "No justification filed."

    inflow = float(report.get("inflow_usd", 0.0)) if report else 0.0
    outflow = float(report.get("outflow_usd", 0.0)) if report else 0.0
    pass_through = float(report.get("pass_through_ratio", 0.0)) if report else 0.0
    quarter = report.get("quarter", "N/A") if report else case.get("quarter", "N/A")
    cash_deposits = float(report.get("cash_usd", 0.0)) if report else 0.0
    overrides = int(report.get("management_overrides", 0)) if report else 0
    sar_delay = int(report.get("days_alert_to_sar", 0)) if report else 0

    # Format relationships
    edge_text = ""
    if edges:
        edge_text = "\n".join(
            f"- **{e.get('edge_type', 'Link')}**: Connected to `{e.get('target_name', 'Counterparty')}` "
            f"({'⚠️ HIDDEN LINK - Not known to bank' if e.get('known_to_bank') == 'No' else 'Known to bank'}) "
            f"| Flow: ${float(e.get('total_usd') or 0):,.0f}"
            for e in edges
        )
    else:
        edge_text = "No direct network edges recorded."

    # Format transactions
    txn_text = ""
    if transactions:
        txn_text = "\n".join(
            f"- `{t.get('date', 'N/A')}` | `{t.get('type', 'Wire')}` | Amount: **${float(t.get('amount_usd') or 0):,.0f}** "
            f"| From: {t.get('from_name')} ({t.get('from_country')}) → To: {t.get('to_name')} ({t.get('to_country')}) "
            f"| Reference: *{t.get('purpose', 'N/A')}*"
            for t in transactions[:8]
        )
    else:
        txn_text = "No individual transaction records available."

    dossier = f"""# EIDGENÖSSISCHE FINANZMARKTAUFSICHT (FINMA)
## Money Laundering Reporting Office (MROS) — Formal Supervisory Dossier
**Document Reference:** `SAR-DOSSIER/{case_id}`  
**Generated At:** `{now_str}`  
**Classification:** STRICTLY CONFIDENTIAL // REGULATORY ENFORCEMENT

---

### 1. Case & Investigation Metadata
| Field | Value |
|---|---|
| **Case File ID** | `{case_id}` |
| **Subject Legal Name** | **{entity_name}** |
| **Entity Identifier** | `{entity_id}` |
| **Reporting Swiss Bank** | **{bank}** |
| **Supervisory Risk Score** | **{risk_score:.0f} / 100 (HIGH RISK — MANDATORY ESCALATION)** |
| **Investigation Status** | `{status}` |
| **Assigned Investigator** | `{supervisor}` |
| **Review Period** | `{quarter}` |

---

### 2. Subject Profiling & PEP Classification Analysis
- **Legal Entity Type:** {entity.get('entity_type', 'Entity')}
- **Country of Incorporation / Domicile:** `{country}` (Offshore Jurisdiction: **{entity.get('offshore_jurisdiction', 'No')}**)
- **PEP Status Category:** **{pep_cat}**
- **Connected Politically Exposed Person:** `{entity.get('linked_pep_name', 'Self')}` ({entity.get('pep_role', 'Public Function')})
- **Bank's Internal Flagging:** `{entity.get('flagged_as_pep_by_bank', 'No')}`
  > {"⚠️ **REGULATORY BLIND SPOT DETECTED:** Bank failed to identify or flag this entity as PEP-related, circumventing enhanced due diligence." if entity.get('flagged_as_pep_by_bank') != 'Yes' else "Entity was acknowledged as PEP-related by reporting bank."}
- **Source of Wealth / Funds Verification:** `{entity.get('source_of_funds_verified', 'No')}`

---

### 3. Financial Flows & Pass-Through Velocity
During audit quarter **{quarter}**, the subject account experienced abnormal volumetric inflows and rapid outward disbursement consistent with money laundering pass-through behavior:

- **Total Inbound Funds:** `${inflow:,.2f}`
- **Total Outbound Funds:** `${outflow:,.2f}`
- **Pass-Through Ratio:** **{pass_through:.3f}** (Threshold breach >= 0.80)
- **Cash Structuring / Deposits:** `${cash_deposits:,.2f}`
- **High-Risk Destination Share:** `{float(report.get('high_risk_destination_share', 0.0) if report else 0.0):.1%}`

#### Sample Transaction Records
{txn_text}

---

### 4. Governance & Compliance Exception Audit
A forensic review of internal bank actions reveals systemic governance and control circumventions:

1. **Management Overrides:** `{overrides}` instance(s) recorded.
2. **Compliance Exit / SAR Recommendation:** Bank compliance department explicitly recommended account termination or immediate SAR submission, but was **overruled by executive management**.
3. **Documented Management Override Justification:**
   > *"{override_justification}"*
4. **Authority Notification Delay:** Alert was held internally for **{sar_delay} days** before supervisory transmission (Maximum permissible: 90 days).

---

### 5. Identified Network Topology & Hidden Counterparties
{edge_text}

---

### 6. Supervisory Conclusions & Proposed Enforcement Actions
Based on the objective presence of:
- Unverified beneficial ownership within an offshore tax haven;
- Near-perfect pass-through velocity ($\approx {pass_through:.1%}$) of high-volume wire transfers;
- Willful executive override of compliance recommendations;

**FINMA Supervisory Directorate hereby orders:**
1. Immediate transmission of this file to the **Swiss Office of the Attorney General (OAG / MPC)** pursuant to Article 29 AMLA.
2. Formal demand upon **{bank}** for complete transaction ledgers and correspondence files touching `{entity_id}` within 5 business days.
3. Initiation of administrative enforcement proceedings regarding governance circumvention and PEP onboarding failures under Article 37 FINMASA.

**Investigator Notes:**
{investigation_notes}

---
*End of Dossier // Generated automatically by FINMA PEP Supervisory Analytics Engine*
"""
    return dossier