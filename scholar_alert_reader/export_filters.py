"""Filters for user-facing exports.

The ranking layer keeps internal feedback terms such as ``similar:...`` and
``user:...`` so future runs can learn from feedback. Downstream tools like
Zotero and Obsidian should not receive those implementation details as tags.
"""

from __future__ import annotations

from typing import Any, Iterable


INTERNAL_EXPORT_PREFIXES = ("similar:", "dissimilar:", "user:", "user:-")
INTERNAL_EXPORT_TAGS = {"adaptive", "feedback", "semantic", "watchlist"}


def export_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def is_internal_export_term(value: Any) -> bool:
    term = export_text(value).lower()
    return term.startswith(INTERNAL_EXPORT_PREFIXES)


def public_export_terms(values: Iterable[Any]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = export_text(value)
        if not term or is_internal_export_term(term):
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def public_export_tags(values: Iterable[Any]) -> list[str]:
    return [term for term in public_export_terms(values) if term.lower() not in INTERNAL_EXPORT_TAGS]


def public_export_keywords(matched_terms: Iterable[Any], tags: Iterable[Any]) -> list[str]:
    return public_export_terms(matched_terms) + [
        tag for tag in public_export_tags(tags) if tag.lower() not in {term.lower() for term in public_export_terms(matched_terms)}
    ]
