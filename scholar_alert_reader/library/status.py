"""Shared feedback status helpers for paper records.

This module intentionally does not depend on optional/experimental reporting
layers and can be used by both core/library and copilot-style readers.
"""

from __future__ import annotations

from typing import Any


def feedback_record(record: dict[str, Any], feedback: dict[str, Any] | None) -> dict[str, Any]:
    """Return feedback entry for a paper id."""

    if not isinstance(feedback, dict):
        return {}
    item = feedback.get("papers", {}).get(str(record.get("id", "")), {})
    return item if isinstance(item, dict) else {}


def reading_status(record: dict[str, Any], feedback: dict[str, Any] | None) -> str:
    """Resolve effective reading status for rendering and filters."""

    item = feedback_record(record, feedback)
    status = str(item.get("reading_status", "") or "")
    if status:
        return status
    if item.get("status") == "archive":
        return "not-relevant"
    if item.get("status") == "interested" or record.get("tier") == "Must read":
        return "unread"
    return "unread"


def priority_override(record: dict[str, Any], feedback: dict[str, Any] | None) -> str:
    """Resolve an optional manual tier override from feedback."""

    item = feedback_record(record, feedback)
    value = str(item.get("priority_override", "") or "").strip().lower().replace("-", "_")
    if value in {"must_read", "skim", "archive"}:
        return value
    return ""


def reading_labels(record: dict[str, Any], feedback: dict[str, Any] | None) -> list[str]:
    item = feedback_record(record, feedback)
    labels = item.get("labels", [])
    if isinstance(labels, list):
        return [str(label) for label in labels if str(label).strip()]
    return []


def feedback_note(record: dict[str, Any], feedback: dict[str, Any] | None, limit: int = 1200) -> str:
    note = str(feedback_record(record, feedback).get("note", "") or "").strip()
    if not note:
        return ""
    if limit <= 0 or len(note) <= limit:
        return note
    return note[:limit].rstrip() + f"\n\n[Truncated to {limit} characters.]"


def feedback_note_summary(record: dict[str, Any], feedback: dict[str, Any] | None, limit: int = 280) -> str:
    """Compact single-line note summary."""

    note = " ".join(feedback_note(record, feedback, limit=limit + 80).split())
    if limit <= 0 or len(note) <= limit:
        return note
    return note[:limit].rstrip() + "..."


def record_source_types(record: dict[str, Any]) -> list[str]:
    """Resolve broad ingestion source types without exposing alert names as types."""

    source_types: list[str] = []

    def add(value: str) -> None:
        value = value.strip().lower()
        if value and value not in source_types:
            source_types.append(value)

    raw_source_types = record.get("source_types", [])
    if isinstance(raw_source_types, list):
        for source_type in raw_source_types:
            add(str(source_type))

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    if isinstance(metadata, dict):
        if "arxiv" in metadata:
            add("arxiv")
        if "feed" in metadata:
            add("rss")
        if "bibtex" in metadata:
            add("bibtex")
        if "ris" in metadata:
            add("ris")
        if "web" in metadata:
            add("web")
        if "zotero" in metadata:
            add("zotero")

    alerts = record.get("alerts", [])
    if isinstance(alerts, list):
        alert_text = " ".join(str(alert).lower() for alert in alerts)
        if "atom/rss import" in alert_text or "rss import" in alert_text or "rss" in alert_text:
            add("rss")
        if "bibtex import" in alert_text:
            add("bibtex")
        if "ris import" in alert_text:
            add("ris")
        if "web metadata import" in alert_text:
            add("web")
        if not source_types:
            add("google-scholar-alert")

    return source_types
