"""Review-only fuzzy duplicate detection for a local paper universe.

The functions in this module deliberately stop at candidate generation.  They
never mutate input records or apply merges: a person must decide whether two
records describe the same scholarly work.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "via",
    "with",
}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
REVIEW_STATUSES = {"unreviewed", "reviewed"}
REVIEW_DECISIONS = {"same-work", "distinct-works", "unsure"}


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[\w]+", text, flags=re.UNICODE))


def normalize_title(value: Any) -> str:
    return normalize_text(value)


def title_tokens(value: Any, *, significant: bool = False) -> list[str]:
    tokens = normalize_title(value).split()
    if not significant:
        return tokens
    return [token for token in tokens if token not in TITLE_STOPWORDS and (len(token) >= 3 or token.isdigit())]


def title_similarity_details(left: Any, right: Any) -> dict[str, float]:
    left_normalized = normalize_title(left)
    right_normalized = normalize_title(right)
    left_terms = set(title_tokens(left, significant=True))
    right_terms = set(title_tokens(right, significant=True))
    if not left_normalized or not right_normalized or not left_terms or not right_terms:
        return {"score": 0.0, "token_jaccard": 0.0, "token_containment": 0.0, "sequence_ratio": 0.0}
    shared = len(left_terms & right_terms)
    token_jaccard = shared / len(left_terms | right_terms)
    token_containment = shared / min(len(left_terms), len(right_terms))
    sequence_ratio = SequenceMatcher(None, left_normalized, right_normalized, autojunk=False).ratio()
    containment_score = token_containment * 0.95 if min(len(left_terms), len(right_terms)) >= 4 else 0.0
    score = max(token_jaccard, sequence_ratio, containment_score)
    return {
        "score": round(score, 4),
        "token_jaccard": round(token_jaccard, 4),
        "token_containment": round(token_containment, 4),
        "sequence_ratio": round(sequence_ratio, 4),
    }


def title_similarity(left: Any, right: Any) -> float:
    return title_similarity_details(left, right)["score"]


def record_sources(record: dict[str, Any]) -> list[str]:
    values = coerce_list(record.get("source_types") or record.get("source_type"))
    return sorted({normalize_text(value).replace(" ", "_") for value in values if normalize_text(value)})


def record_id(record: dict[str, Any]) -> str:
    value = str(record.get("paper_id") or record.get("id") or "").strip()
    if value:
        return value
    identity = f"{normalize_title(record.get('title'))}|{','.join(record_sources(record))}"
    return hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _year_from_value(value: Any) -> int | None:
    if isinstance(value, int) and 1800 <= value <= 2199:
        return value
    match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value or ""))
    return int(match.group(0)) if match else None


def record_year(record: dict[str, Any]) -> int | None:
    for field in ["year", "publication_year", "date", "issued"]:
        year = _year_from_value(record.get(field))
        if year:
            return year
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for provider in ["openalex", "zotero", "bibtex", "ris", "crossref", "web"]:
            item = metadata.get(provider)
            if not isinstance(item, dict):
                continue
            for field in ["publication_year", "year", "date", "issued"]:
                year = _year_from_value(item.get(field))
                if year:
                    return year
    year = _year_from_value(record.get("authors_source"))
    return year


def _author_name(value: Any) -> str:
    if isinstance(value, dict):
        for field in ["name", "display_name", "literal"]:
            if value.get(field):
                return " ".join(str(value[field]).split())
        family = str(value.get("family") or value.get("last") or value.get("last_name") or "").strip()
        given = str(value.get("given") or value.get("first") or value.get("first_name") or "").strip()
        return " ".join(part for part in [given, family] if part)
    return " ".join(str(value or "").split())


def _first_author_from_value(value: Any) -> str:
    values = coerce_list(value)
    if not values:
        return ""
    first = values[0]
    if isinstance(first, dict):
        return _author_name(first)
    text = _author_name(first)
    if not text:
        return ""
    parts = re.split(r"\s+and\s+|\s*;\s*", text, maxsplit=1, flags=re.IGNORECASE)
    return parts[0].strip()


def record_first_author(record: dict[str, Any]) -> str:
    for field in ["authors", "author", "first_author"]:
        author = _first_author_from_value(record.get(field))
        if author:
            return author
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for provider in ["openalex", "zotero", "bibtex", "ris", "crossref", "web"]:
            item = metadata.get(provider)
            if not isinstance(item, dict):
                continue
            for field in ["authors", "author", "first_author"]:
                author = _first_author_from_value(item.get(field))
                if author:
                    return author
    source_records = record.get("source_records")
    if isinstance(source_records, dict):
        for item in source_records.values():
            if not isinstance(item, dict):
                continue
            for field in ["authors", "author", "first_author"]:
                author = _first_author_from_value(item.get(field))
                if author:
                    return author
    source = str(record.get("authors_source") or "").split(" - ", 1)[0].strip()
    return _first_author_from_value(source)


def normalize_author(value: Any) -> str:
    text = " ".join(str(value or "").replace("{", "").replace("}", "").split())
    if not text:
        return ""
    before_comma = text.split(",", 1)[0].strip()
    tokens = normalize_text(before_comma).split()
    if not tokens:
        return ""
    suffixes = {"ii", "iii", "iv", "jr", "sr"}
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return tokens[-1] if tokens else ""


def normalize_doi(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.strip().rstrip(".,;)")


def record_dois(record: dict[str, Any]) -> set[str]:
    dois: set[str] = set()

    def add(value: Any) -> None:
        for item in coerce_list(value):
            doi = normalize_doi(item)
            if doi:
                dois.add(doi)

    add(record.get("doi"))
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for item in metadata.values():
            if isinstance(item, dict):
                add(item.get("doi"))
    source_records = record.get("source_records")
    if isinstance(source_records, dict):
        for item in source_records.values():
            if isinstance(item, dict):
                add(item.get("doi"))
    return dois


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    dois = sorted(record_dois(record))
    collections = [str(value) for value in coerce_list(record.get("zotero_collections")) if str(value).strip()]
    return {
        "id": record_id(record),
        "title": " ".join(str(record.get("title") or "Untitled").split()),
        "year": record_year(record),
        "first_author": record_first_author(record),
        "source_types": record_sources(record),
        "doi": dois[0] if dois else "",
        "zotero_collections": collections,
        "url": str(record.get("url") or record.get("scholar_url") or "").strip(),
    }


def _confidence(
    score: float,
    *,
    exact_title: bool,
    doi_match: bool,
    year_match: bool | None,
    first_author_match: bool | None,
) -> str:
    corroborating = sum(value is True for value in [year_match, first_author_match])
    if doi_match or (exact_title and corroborating >= 1):
        return "high"
    if score >= 0.90 and corroborating >= 1:
        return "high"
    if score >= 0.82 and corroborating == 2:
        return "high"
    if score >= 0.82 and corroborating >= 1:
        return "medium"
    if score >= 0.72 and corroborating == 2:
        return "medium"
    return "low"


def _candidate_id(left: dict[str, Any], right: dict[str, Any], left_source: str, right_source: str) -> str:
    identity = f"{left_source}:{record_id(left)}|{right_source}:{record_id(right)}"
    return "dup-" + hashlib.sha1(identity.encode("utf-8", errors="ignore")).hexdigest()[:12]


def find_duplicate_candidates(
    records: list[dict[str, Any]],
    *,
    left_source: str = "scholar_alert",
    right_source: str = "zotero",
    title_threshold: float = 0.72,
    year_tolerance: int = 2,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return cross-source candidates without mutating or merging records."""
    if not 0.0 <= title_threshold <= 1.0:
        raise ValueError("title_threshold must be between 0 and 1")
    if year_tolerance < 0:
        raise ValueError("year_tolerance must be non-negative")

    normalized_left = normalize_text(left_source).replace(" ", "_")
    normalized_right = normalize_text(right_source).replace(" ", "_")
    left_records = [
        record
        for record in records
        if normalized_left in set(record_sources(record)) and normalized_right not in set(record_sources(record))
    ]
    right_records = [
        record
        for record in records
        if normalized_right in set(record_sources(record)) and normalized_left not in set(record_sources(record))
    ]

    token_index: dict[str, set[int]] = defaultdict(set)
    right_token_sets: list[set[str]] = []
    for index, record in enumerate(right_records):
        tokens = set(title_tokens(record.get("title"), significant=True))
        right_token_sets.append(tokens)
        for token in tokens:
            token_index[token].add(index)

    candidates: list[dict[str, Any]] = []
    for left in left_records:
        left_tokens = set(title_tokens(left.get("title"), significant=True))
        if not left_tokens:
            continue
        possible_indexes: set[int] = set()
        for token in left_tokens:
            possible_indexes.update(token_index.get(token, set()))
        for index in possible_indexes:
            right = right_records[index]
            right_tokens = right_token_sets[index]
            shared_tokens = left_tokens & right_tokens
            minimum_shared = 1 if min(len(left_tokens), len(right_tokens)) <= 3 else 2
            if len(shared_tokens) < minimum_shared:
                continue
            similarity = title_similarity_details(left.get("title"), right.get("title"))
            score = similarity["score"]
            if score < title_threshold:
                continue

            left_year = record_year(left)
            right_year = record_year(right)
            year_difference = abs(left_year - right_year) if left_year is not None and right_year is not None else None
            if year_difference is not None and year_difference > year_tolerance:
                continue
            year_match = year_difference <= year_tolerance if year_difference is not None else None

            left_author = record_first_author(left)
            right_author = record_first_author(right)
            left_author_key = normalize_author(left_author)
            right_author_key = normalize_author(right_author)
            first_author_match = (
                left_author_key == right_author_key if left_author_key and right_author_key else None
            )
            shared_dois = sorted(record_dois(left) & record_dois(right))
            exact_title = normalize_title(left.get("title")) == normalize_title(right.get("title"))
            confidence = _confidence(
                score,
                exact_title=exact_title,
                doi_match=bool(shared_dois),
                year_match=year_match,
                first_author_match=first_author_match,
            )
            rank_score = score
            rank_score += 0.12 if shared_dois else 0.0
            rank_score += 0.04 if year_match is True else 0.0
            rank_score += 0.05 if first_author_match is True else 0.0
            candidates.append(
                {
                    "schema_version": 1,
                    "candidate_id": _candidate_id(left, right, normalized_left, normalized_right),
                    "confidence": confidence,
                    "match_score": round(rank_score, 4),
                    "evidence": {
                        **similarity,
                        "exact_title": exact_title,
                        "shared_title_tokens": sorted(shared_tokens),
                        "left_year": left_year,
                        "right_year": right_year,
                        "year_difference": year_difference,
                        "year_match": year_match,
                        "left_first_author_key": left_author_key,
                        "right_first_author_key": right_author_key,
                        "first_author_match": first_author_match,
                        "doi_match": bool(shared_dois),
                        "shared_dois": shared_dois,
                    },
                    "left": _record_summary(left),
                    "right": _record_summary(right),
                    "suggested_action": "manual_review",
                    "review_status": "unreviewed",
                    "review_decision": None,
                    "review_notes": "",
                }
            )

    candidates.sort(
        key=lambda item: (
            CONFIDENCE_ORDER.get(str(item["confidence"]), 9),
            -float(item["match_score"]),
            str(item["left"]["title"]).casefold(),
            str(item["right"]["title"]).casefold(),
        )
    )
    return candidates[:limit] if limit > 0 else candidates


def source_pair_counts(
    records: list[dict[str, Any]], left_source: str = "scholar_alert", right_source: str = "zotero"
) -> tuple[int, int]:
    left = normalize_text(left_source).replace(" ", "_")
    right = normalize_text(right_source).replace(" ", "_")
    left_count = sum(left in set(record_sources(record)) and right not in set(record_sources(record)) for record in records)
    right_count = sum(right in set(record_sources(record)) and left not in set(record_sources(record)) for record in records)
    return left_count, right_count


def _md(value: Any) -> str:
    return " ".join(str(value or "").replace("|", "\\|").split())


def _short(value: Any, limit: int = 82) -> str:
    text = _md(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_duplicate_report(
    candidates: list[dict[str, Any]],
    *,
    universe_path: Path,
    total_records: int,
    left_source: str = "scholar_alert",
    right_source: str = "zotero",
    left_records: int | None = None,
    right_records: int | None = None,
    title_threshold: float = 0.72,
    year_tolerance: int = 2,
) -> str:
    counts = Counter(str(item.get("confidence", "low")) for item in candidates)
    lines = [
        "# Fuzzy Duplicate Review",
        "",
        "This is a review-only data-quality report. It does not merge or modify paper-universe records.",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Paper universe: `{universe_path}`",
        f"- Universe records: {total_records}",
        f"- Source pair: `{left_source}` ↔ `{right_source}`",
    ]
    if left_records is not None and right_records is not None:
        lines.extend([f"- Left-only records: {left_records}", f"- Right-only records: {right_records}"])
    lines.extend(
        [
            f"- Title threshold: {title_threshold:.2f}",
            f"- Year tolerance: ±{year_tolerance}",
            f"- Candidates: {len(candidates)} (high {counts['high']} / medium {counts['medium']} / low {counts['low']})",
            "",
            "## Review Protocol",
            "",
            "Review the JSONL worksheet alongside this report. For each candidate, keep `review_status` as `unreviewed` or set it to `reviewed`; set `review_decision` to `same-work`, `distinct-works`, or `unsure`, and add `review_notes` when useful.",
            "",
            "A high confidence label is still only a prioritization hint. DOI, title, year, and first-author evidence can be incomplete or wrong, so no decision is applied automatically.",
            "",
        ]
    )
    if not candidates:
        lines.append("No candidates met the current review thresholds.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        [
            "## Candidates",
            "",
            "| ID | Confidence | Review | Title score | Year | First author | Left record | Right record | Evidence |",
            "|---|---|---|---:|---|---|---|---|---|",
        ]
    )
    for candidate in candidates:
        evidence = candidate["evidence"]
        left = candidate["left"]
        right = candidate["right"]
        year = "?"
        if evidence.get("left_year") or evidence.get("right_year"):
            year = f"{evidence.get('left_year') or '?'} ↔ {evidence.get('right_year') or '?'}"
            if evidence.get("year_difference") is not None:
                year += f" (Δ{evidence['year_difference']})"
        authors = f"{left.get('first_author') or '?'} ↔ {right.get('first_author') or '?'}"
        details: list[str] = []
        if evidence.get("shared_dois"):
            details.append("DOI " + ", ".join(evidence["shared_dois"]))
        if evidence.get("exact_title"):
            details.append("exact normalized title")
        if evidence.get("first_author_match") is True:
            details.append("first author matches")
        elif evidence.get("first_author_match") is False:
            details.append("first author differs")
        if evidence.get("year_match") is True:
            details.append("year compatible")
        details.append("shared: " + ", ".join(evidence.get("shared_title_tokens", [])[:8]))
        review = str(candidate.get("review_status") or "unreviewed")
        if candidate.get("review_decision"):
            review += f" / {candidate['review_decision']}"
        lines.append(
            f"| `{candidate['candidate_id']}` | {candidate['confidence']} | {_md(review)} | {evidence['score']:.3f} | {_md(year)} | {_md(authors)} | {_short(left['title'])} (`{_md(left['id'])}`) | {_short(right['title'])} (`{_md(right['id'])}`) | {_md('; '.join(details))} |"
        )
    lines.append("")
    return "\n".join(lines)


def carry_forward_reviews(path: Path, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve explicit human decisions when regenerating a candidate worksheet."""
    if not path.exists():
        return candidates
    existing: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return candidates
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and str(item.get("candidate_id") or ""):
            existing[str(item["candidate_id"])] = item

    refreshed: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        previous = existing.get(str(candidate.get("candidate_id") or ""), {})
        status = str(previous.get("review_status") or "")
        decision = previous.get("review_decision")
        notes = previous.get("review_notes")
        if status in REVIEW_STATUSES:
            item["review_status"] = status
        if decision in REVIEW_DECISIONS:
            item["review_decision"] = decision
        if isinstance(notes, str):
            item["review_notes"] = notes
        refreshed.append(item)
    return refreshed


def write_duplicate_candidates(path: Path, candidates: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n" for candidate in candidates),
        encoding="utf-8",
    )
    return path
