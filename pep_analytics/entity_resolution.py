"""Entity Resolution and Fuzzy Name Matching for PEP Supervisory Intelligence.

Detects aliases, spelling variations, initial contractions, and corporate suffixes
against known PEP entities to prevent blind spots and duplicate account evasions.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

import pandas as pd

# Common titles and corporate entity noise to strip during token comparison
_PREFIXES = {"dr", "judge", "ambassador", "minister", "sheikh", "mr", "mrs", "ms", "advocate"}
_CORP_SUFFIXES = {
    "ltd", "corp", "inc", "sa", "sarl", "sal", "holding", "holdings",
    "services", "co", "company", "trust", "group", "advisory", "international"
}


def _tokenize_and_normalize(name: str) -> list[str]:
    """Lowercase, strip punctuation, remove noise words, return list of tokens."""
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    tokens = [t for t in cleaned.split() if t]
    filtered = [t for t in tokens if t not in _PREFIXES and t not in _CORP_SUFFIXES]
    return filtered or tokens


def _initials_match(tokens_a: list[str], tokens_b: list[str]) -> bool:
    """Check if one name is an initial-contracted version of the other.

    e.g. ['r', 'salameh'] matches ['riad', 'salameh'] or ['r', 'k', 'salameh']
    """
    if not tokens_a or not tokens_b:
        return False

    # Check last name / primary token match
    if tokens_a[-1] != tokens_b[-1]:
        return False

    # Check that initials match for remaining tokens
    short_tokens = tokens_a if len(tokens_a) <= len(tokens_b) else tokens_b
    long_tokens = tokens_b if len(tokens_a) <= len(tokens_b) else tokens_a

    matched_initials = 0
    for s in short_tokens[:-1]:
        init = s[0]
        if any(l[0] == init for l in long_tokens[:-1]):
            matched_initials += 1

    return matched_initials > 0 and matched_initials == len(short_tokens[:-1])


def calculate_name_similarity(name_a: str, name_b: str) -> tuple[float, str]:
    """Calculate matching score between two names (0.0 to 1.0) and match rationale."""
    if not name_a or not name_b:
        return 0.0, "Empty name"

    norm_a = name_a.strip().lower()
    norm_b = name_b.strip().lower()

    if norm_a == norm_b:
        return 1.0, "Exact match"

    tokens_a = _tokenize_and_normalize(name_a)
    tokens_b = _tokenize_and_normalize(name_b)

    # Check initial contraction
    if _initials_match(tokens_a, tokens_b):
        return 0.90, "Initial contraction / Alias match"

    # Token overlap (Jaccard-like)
    set_a, set_b = set(tokens_a), set(tokens_b)
    overlap = set_a & set_b
    if overlap:
        overlap_score = len(overlap) / max(len(set_a), len(set_b))
        if overlap_score >= 0.7:
            return round(overlap_score * 0.95, 2), "High token overlap"

    # Sequence string similarity
    ratio = difflib.SequenceMatcher(None, " ".join(tokens_a), " ".join(tokens_b)).ratio()

    # Boost if the primary surname / token matches
    if tokens_a and tokens_b and tokens_a[-1] == tokens_b[-1] and ratio >= 0.65:
        ratio = min(1.0, ratio + 0.15)
        return round(ratio, 2), "Surname match with high phonetic similarity"

    if ratio >= 0.75:
        return round(ratio, 2), "Close spelling variation"

    return round(ratio, 2), "Low similarity"


def find_matching_entities(
    query_name: str,
    entities_df: pd.DataFrame,
    threshold: float = 0.70,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Scan existing database entities for potential matches to query_name.

    Returns list of dicts with match details, sorted by descending score.
    """
    if not query_name or entities_df.empty:
        return []

    results = []
    seen_ids = set()

    for _, row in entities_df.iterrows():
        ent_name = str(row.get("name") or "")
        if not ent_name:
            continue

        score, reason = calculate_name_similarity(query_name, ent_name)
        if score >= threshold:
            eid = row.get("entity_id")
            if eid not in seen_ids:
                seen_ids.add(eid)
                results.append({
                    "entity_id": eid,
                    "matched_name": ent_name,
                    "score": score,
                    "confidence_pct": int(score * 100),
                    "reason": reason,
                    "pep_category": row.get("pep_category", "Unknown"),
                    "swiss_bank": row.get("swiss_bank", "Unknown"),
                    "flagged_by_bank": row.get("flagged_as_pep_by_bank", "No"),
                    "country": row.get("country", ""),
                })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
