"""Shared domain models for the literature triage pipeline.

This module is intentionally lightweight and is the first step of a gradual
core refactor.  It is used as the canonical vocabulary for new modules while
the existing pipeline keeps backward-compatible behavior in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawItem:
    """A source row before normalization."""

    source_type: str
    source_id: str | None
    raw_title: str
    raw_authors: str | None = None
    raw_snippet: str | None = None
    raw_url: str | None = None
    raw_date: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperRecord:
    """Normalized paper record used by ranking and library layers."""

    paper_id: str
    title: str
    normalized_title: str
    authors: list[str]
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    source_types: list[str] = field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    source_records: list[RawItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreComponent:
    """One named contribution to an aggregate score."""

    name: str
    value: float
    matched_terms: list[str]
    explanation: str
    evidence_field: str | None = None


@dataclass
class ScoredPaper:
    paper: PaperRecord
    final_score: float
    tier: str
    score_components: list[ScoreComponent] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FeedbackRecord:
    paper_id: str
    status: str
    reading_status: str | None = None
    labels: list[str] = field(default_factory=list)
    note: str | None = None
    more_like_this: bool = False
    less_like_this: bool = False
    updated_at: str = ""


@dataclass
class LibraryRecord:
    paper: PaperRecord
    score: ScoredPaper
    feedback: FeedbackRecord | None = None

