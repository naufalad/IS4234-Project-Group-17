"""Detection-quality validation against the answer key.

This is the ONLY module permitted to read the answer-key columns
(``is_suspicious``, ``scenario``, ``typology``). Requirements 9.1-9.3.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def _is_yes(value) -> bool:
    return str(value).strip().lower() == "yes"


@dataclass
class Metrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
        }


def evaluate_escalations(scored: pd.DataFrame) -> Metrics:
    """Precision/recall of escalation vs the ``is_suspicious`` answer key (Req 9.1).

    Prediction = escalate_to_finma == Yes. Ground truth = is_suspicious == Yes.
    """
    pred = scored["escalate_to_finma"].apply(_is_yes)
    truth = scored["is_suspicious"].apply(_is_yes)
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    tn = int((~pred & ~truth).sum())
    return Metrics(tp, fp, fn, tn)


def bank_missed_but_caught(scored: pd.DataFrame) -> pd.DataFrame:
    """Suspicious client-quarters the bank did not flag that we escalated (Req 9.2).

    i.e. is_suspicious == Yes AND flagged_as_pep_by_bank != Yes AND we escalated.
    """
    truth = scored["is_suspicious"].apply(_is_yes)
    not_flagged = ~scored["flagged_as_pep_by_bank"].apply(_is_yes)
    caught = scored["escalate_to_finma"].apply(_is_yes)
    mask = truth & not_flagged & caught
    cols = [c for c in ["quarter", "entity_id", "name", "swiss_bank",
                        "pep_category", "risk_score", "scenario"]
            if c in scored.columns]
    return scored.loc[mask, cols].sort_values("risk_score", ascending=False)


def transactions_missed_but_relevant(transactions: pd.DataFrame) -> dict:
    """Count suspicious transactions the bank's own system did not alert on (Req 9.2)."""
    truth = transactions["is_suspicious"].apply(_is_yes)
    alerted = transactions["bank_raised_alert"].apply(_is_yes)
    return {
        "suspicious_total": int(truth.sum()),
        "suspicious_not_alerted_by_bank": int((truth & ~alerted).sum()),
        "suspicious_alerted_by_bank": int((truth & alerted).sum()),
    }
