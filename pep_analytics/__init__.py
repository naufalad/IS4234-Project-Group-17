"""FINMA PEP Supervisory Analytics.

Regulator-side (FINMA) analytics layer over the synthetic ``dataset2/`` tables.
It ingests HSBC's PEP-scoped submissions, re-derives risk independently of the
bank's own alerts, runs network analytics to surface what the bank missed, and
auto-escalates threshold breaches.

Design principle: the answer-key columns (``is_suspicious``, ``scenario``,
``typology``) must never feed scoring, graph analytics, or escalation. They are
consumed only by :mod:`pep_analytics.validation`.
"""

from pep_analytics.config import RiskConfig, DEFAULT_WEIGHTS

__all__ = ["RiskConfig", "DEFAULT_WEIGHTS"]
