"""Metadata enrichment helpers for Scholar Alert Reader.

This module stays dependency-free and uses public scholarly metadata APIs only
for selected papers, not the whole alert stream.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT = 12


@dataclass
class EnrichStats:
    requested: int = 0
    enriched: int = 0
    openalex_hits: int = 0
    crossref_hits: int = 0
    errors: int = 0


def http_json(url: str, user_agent: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def normalized_title(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def title_similarity(left: str, right: str) -> float:
    left_terms = set(normalized_title(left).split())
    right_terms = set(normalized_title(right).split())
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def openalex_lookup(title: str, email: str | None, user_agent: str) -> dict[str, Any] | None:
    params = {"search": title, "per-page": "3"}
    if email:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urlencode(params)
    data = http_json(url, user_agent)
    candidates = data.get("results", [])
    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in candidates:
        score = title_similarity(title, str(item.get("title", "")))
        if score > best_score:
            best = item
            best_score = score
    if not best or best_score < 0.35:
        return None
    authors = []
    for authorship in best.get("authorships", [])[:12]:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)
    locations = best.get("locations") or []
    primary_location = best.get("primary_location") or (locations[0] if locations else {})
    source = (primary_location.get("source") or {}) if isinstance(primary_location, dict) else {}
    return {
        "id": best.get("id"),
        "doi": best.get("doi"),
        "title": best.get("title"),
        "publication_year": best.get("publication_year"),
        "cited_by_count": best.get("cited_by_count"),
        "type": best.get("type"),
        "open_access": best.get("open_access"),
        "authors": authors,
        "source": source.get("display_name"),
        "landing_page_url": primary_location.get("landing_page_url") if isinstance(primary_location, dict) else None,
        "pdf_url": primary_location.get("pdf_url") if isinstance(primary_location, dict) else None,
        "match_score": round(best_score, 3),
    }


def crossref_lookup(title: str, email: str | None, user_agent: str) -> dict[str, Any] | None:
    params = {"query.title": title, "rows": "3"}
    if email:
        params["mailto"] = email
    url = "https://api.crossref.org/works?" + urlencode(params)
    data = http_json(url, user_agent)
    candidates = ((data.get("message") or {}).get("items") or [])
    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in candidates:
        candidate_title = " ".join(item.get("title") or [])
        score = title_similarity(title, candidate_title)
        if score > best_score:
            best = item
            best_score = score
    if not best or best_score < 0.35:
        return None
    container = best.get("container-title") or []
    return {
        "doi": best.get("DOI"),
        "title": " ".join(best.get("title") or []),
        "container_title": container[0] if container else None,
        "publisher": best.get("publisher"),
        "published": best.get("published-print") or best.get("published-online") or best.get("created"),
        "type": best.get("type"),
        "is_referenced_by_count": best.get("is-referenced-by-count"),
        "url": best.get("URL"),
        "match_score": round(best_score, 3),
    }


def enrich_record(
    record: dict[str, Any],
    providers: set[str],
    email: str | None,
    user_agent: str,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, int]]:
    title = str(record.get("title", "")).strip()
    metadata = dict(record.get("metadata") or {})
    counts = {"openalex": 0, "crossref": 0, "errors": 0}
    if not title:
        return record, counts

    if "openalex" in providers and not metadata.get("openalex"):
        try:
            hit = openalex_lookup(title, email, user_agent)
            if hit:
                metadata["openalex"] = hit
                counts["openalex"] += 1
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            counts["errors"] += 1
        time.sleep(timeout / 100)

    if "crossref" in providers and not metadata.get("crossref"):
        try:
            hit = crossref_lookup(title, email, user_agent)
            if hit:
                metadata["crossref"] = hit
                counts["crossref"] += 1
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            counts["errors"] += 1
        time.sleep(timeout / 100)

    record["metadata"] = metadata
    return record, counts


def enrich_records(
    records: list[dict[str, Any]],
    providers: list[str],
    limit: int,
    email: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[list[dict[str, Any]], EnrichStats]:
    provider_set = {provider.lower() for provider in providers}
    user_agent = "scholar-alert-reader/0.2"
    if email:
        user_agent += f" (mailto:{email})"

    stats = EnrichStats()
    enriched_records: list[dict[str, Any]] = []
    ranked = sorted(
        enumerate(records),
        key=lambda item: (
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(str(item[1].get("tier", "")), 9),
            -int(item[1].get("score", 0) or 0),
            str(item[1].get("title", "")).lower(),
        ),
    )
    target_indexes = {index for index, _ in ranked[: max(0, limit)]}

    for index, record in enumerate(records):
        if index not in target_indexes:
            enriched_records.append(record)
            continue
        stats.requested += 1
        updated, counts = enrich_record(record, provider_set, email, user_agent, timeout)
        stats.openalex_hits += counts["openalex"]
        stats.crossref_hits += counts["crossref"]
        stats.errors += counts["errors"]
        if counts["openalex"] or counts["crossref"]:
            stats.enriched += 1
        enriched_records.append(updated)

    return enriched_records, stats
