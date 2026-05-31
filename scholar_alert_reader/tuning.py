"""Profile tuning suggestions from retained papers and user feedback."""

from __future__ import annotations

import shlex
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .copilot import paper_line, text, tokens


GENERIC_TERMS = {
    "archive",
    "background",
    "boost",
    "feedback",
    "focus",
    "method",
    "methods",
    "monitoring",
    "paper",
    "region",
    "semantic",
    "study",
    "uncategorized",
    "watchlist",
}


def normalized_profile_terms(profile: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for section in ["focus_terms", "regions", "methods", "semantic_queries", "watch_authors", "exclude_terms"]:
        for item in profile.get(section, []):
            if isinstance(item, dict):
                term = text(item.get("term")).strip().lower()
            else:
                term = text(item).strip().lower()
            if term:
                values.add(term)
    return values


def clean_candidate(term: str) -> str:
    term = " ".join(term.replace("user:", "").replace("user:-", "").strip("- ").split())
    return term


def internal_feedback_candidate(term: str) -> bool:
    lowered = term.strip().lower()
    return lowered.startswith(("similar:", "dissimilar:"))


def useful_candidate(term: str) -> bool:
    cleaned = clean_candidate(term)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if internal_feedback_candidate(lowered):
        return False
    if lowered in GENERIC_TERMS:
        return False
    if len(lowered) < 4:
        return False
    return True


def feedback_paper_ids(feedback: dict[str, Any]) -> tuple[set[str], set[str]]:
    positive: set[str] = set()
    negative: set[str] = set()
    for paper_id, item in feedback.get("papers", {}).items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "neutral"))
        reading = str(item.get("reading_status", ""))
        signals = item.get("signals", {}) if isinstance(item.get("signals"), dict) else {}
        if reading == "background-only":
            continue
        if status == "interested" or reading in {"reading", "read", "must-cite", "method-reference"} or signals.get("more_like_this"):
            positive.add(str(paper_id))
        if status == "archive" or reading == "not-relevant" or signals.get("less_like_this"):
            negative.add(str(paper_id))
    return positive, negative


def candidate_terms(record: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for term in record.get("matched_terms", []):
        cleaned = clean_candidate(str(term))
        if useful_candidate(cleaned):
            terms.append(cleaned)
    for tag in record.get("tags", []):
        cleaned = clean_candidate(str(tag))
        if useful_candidate(cleaned):
            terms.append(cleaned)
    if not terms:
        for token in sorted(tokens(text(record.get("title", "")))):
            if useful_candidate(token):
                terms.append(token)
    return sorted(set(terms), key=lambda value: value.lower())


def count_feedback_terms(
    records: list[dict[str, Any]],
    feedback: dict[str, Any],
) -> tuple[Counter[str], Counter[str], dict[str, list[dict[str, Any]]]]:
    positive_ids, negative_ids = feedback_paper_ids(feedback)
    positive: Counter[str] = Counter()
    negative: Counter[str] = Counter()
    evidence: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        paper_id = text(record.get("id"))
        terms = candidate_terms(record)
        if paper_id in positive_ids:
            positive.update(terms)
            for term in terms:
                evidence.setdefault(term, []).append(record)
        if paper_id in negative_ids:
            negative.update(terms)
            for term in terms:
                evidence.setdefault(term, []).append(record)

    for item in feedback.get("terms", []):
        if not isinstance(item, dict):
            continue
        term = clean_candidate(text(item.get("term")))
        if not useful_candidate(term):
            continue
        weight = max(1, int(item.get("weight", 1)))
        if item.get("direction") == "negative":
            negative[term] += weight
        else:
            positive[term] += weight
    return positive, negative, evidence


def rank_suggestions(
    positive: Counter[str],
    negative: Counter[str],
    existing: set[str],
    direction: str,
    limit: int,
) -> list[tuple[str, int, int]]:
    suggestions: list[tuple[str, int, int]] = []
    source = positive if direction == "positive" else negative
    opposite = negative if direction == "positive" else positive
    for term, count in source.items():
        if term.lower() in existing:
            continue
        opposing = opposite.get(term, 0)
        if count <= opposing:
            continue
        suggestions.append((term, count, opposing))
    suggestions.sort(key=lambda item: (-(item[1] - item[2]), -item[1], item[0].lower()))
    return suggestions[:limit]


def semantic_query_suggestions(focus_terms: list[tuple[str, int, int]], limit: int) -> list[str]:
    multiword = [term for term, _, _ in focus_terms if len(term.split()) > 1]
    single = [term for term, _, _ in focus_terms if len(term.split()) == 1]
    queries: list[str] = []
    for term in multiword:
        if term.lower() not in {query.lower() for query in queries}:
            queries.append(term)
        if len(queries) >= limit:
            return queries
    if len(single) >= 3:
        queries.append(" ".join(single[:4]))
    return queries[:limit]


def suggest_profile_updates(
    profile: dict[str, Any],
    records: list[dict[str, Any]],
    feedback: dict[str, Any],
    limit: int = 8,
) -> dict[str, Any]:
    positive, negative, evidence = count_feedback_terms(records, feedback)
    existing = normalized_profile_terms(profile)
    focus = rank_suggestions(positive, negative, existing, "positive", limit)
    exclude = rank_suggestions(positive, negative, existing, "negative", limit)
    semantic = [
        query
        for query in semantic_query_suggestions(focus, max(1, min(4, limit)))
        if query.lower() not in existing
    ]
    positive_ids, negative_ids = feedback_paper_ids(feedback)
    return {
        "positive_counts": positive,
        "negative_counts": negative,
        "focus_terms": focus,
        "exclude_terms": exclude,
        "semantic_queries": semantic,
        "evidence": evidence,
        "positive_papers": positive_ids,
        "negative_papers": negative_ids,
    }


def render_profile_tuning_report(
    profile: dict[str, Any],
    records: list[dict[str, Any]],
    feedback: dict[str, Any],
    profile_path: Path,
    limit: int = 8,
) -> str:
    suggestions = suggest_profile_updates(profile, records, feedback, limit=limit)
    lines = [
        "# Profile Tuning Suggestions",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: `{profile_path}`",
        f"- Papers inspected: {len(records)}",
        f"- Positive feedback papers: {len(suggestions['positive_papers'])}",
        f"- Negative feedback papers: {len(suggestions['negative_papers'])}",
        "",
        "This report is based on retained papers and explicit feedback. It is meant to help tune `focus_terms`, `semantic_queries`, and `exclude_terms`; inspect suggestions before applying them.",
        "",
        "## Suggested Focus Terms",
        "",
    ]
    focus_terms = suggestions["focus_terms"]
    if focus_terms:
        for term, count, opposing in focus_terms:
            lines.append(f"- `{term}` - positive signals: {count}; negative signals: {opposing}")
            for record in suggestions["evidence"].get(term, [])[:3]:
                lines.append(f"  - Evidence: {paper_line(record)}")
    else:
        lines.append("- No new focus terms found. Mark more papers as interested/more-like-this first.")
    lines.append("")

    lines.extend(["## Suggested Semantic Queries", ""])
    semantic_queries = suggestions["semantic_queries"]
    if semantic_queries:
        for query in semantic_queries:
            lines.append(f"- `{query}`")
    else:
        lines.append("- No semantic query candidates found yet.")
    lines.append("")

    lines.extend(["## Suggested Exclude Terms", ""])
    exclude_terms = suggestions["exclude_terms"]
    if exclude_terms:
        for term, count, opposing in exclude_terms:
            lines.append(f"- `{term}` - negative signals: {count}; positive signals: {opposing}")
            for record in suggestions["evidence"].get(term, [])[:3]:
                lines.append(f"  - Evidence: {paper_line(record)}")
    else:
        lines.append("- No new exclude terms found. Archive more off-topic papers first.")
    lines.append("")

    focus_csv = ",".join(term for term, _, _ in focus_terms[:5])
    exclude_csv = ",".join(term for term, _, _ in exclude_terms[:5])
    semantic_csv = ",".join(semantic_queries[:3])
    quoted_profile = shlex.quote(str(profile_path))
    lines.extend(["## Apply Commands", ""])
    if focus_csv:
        lines.append(f"- Add focus terms: `python3 scripts/scholar_reader.py feedback --profile {quoted_profile} --more \"{focus_csv}\"`")
    if exclude_csv:
        lines.append(f"- Add exclude terms: `python3 scripts/scholar_reader.py feedback --profile {quoted_profile} --less \"{exclude_csv}\"`")
    if semantic_csv:
        lines.append(f"- Add semantic queries: `python3 scripts/scholar_reader.py profile-tune --profile {quoted_profile} --apply`")
    if not (focus_csv or exclude_csv or semantic_csv):
        lines.append("- No profile update commands to suggest yet.")
    lines.append("")

    lines.extend(["## Current Feedback Signals", ""])
    for label, counter in [("Positive", suggestions["positive_counts"]), ("Negative", suggestions["negative_counts"])]:
        lines.append(f"### {label}")
        if counter:
            lines.append("; ".join(f"`{term}` ({count})" for term, count in counter.most_common(20)))
        else:
            lines.append("No signals yet.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def apply_profile_suggestions(
    profile: dict[str, Any],
    suggestions: dict[str, Any],
    focus_weight: int = 4,
    exclude_weight: int = 4,
    semantic_weight: int = 4,
) -> int:
    changed = 0
    existing = normalized_profile_terms(profile)
    for section, items, weight in [
        ("focus_terms", [term for term, _, _ in suggestions["focus_terms"]], focus_weight),
        ("exclude_terms", [term for term, _, _ in suggestions["exclude_terms"]], exclude_weight),
        ("semantic_queries", suggestions["semantic_queries"], semantic_weight),
    ]:
        target = profile.setdefault(section, [])
        for term in items:
            if term.lower() in existing:
                continue
            tags = ["semantic"] if section == "semantic_queries" else []
            target.append({"term": term, "weight": weight, "tags": tags})
            existing.add(term.lower())
            changed += 1
    return changed
