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
