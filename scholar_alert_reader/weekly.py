"""Weekly literature synthesis rendering."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from .library.status import feedback_note, feedback_note_summary, reading_labels, reading_status


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def paper_line(record: dict[str, Any]) -> str:
    title = str(record.get("title", "Untitled"))
    url = str(record.get("url", ""))
    score = record.get("score", 0)
    tier = record.get("tier", "")
    source = str(record.get("authors_source", ""))
    if url:
        return f"- **[{title}]({url})** ({score}, {tier}) - {source}"
    return f"- **{title}** ({score}, {tier}) - {source}"


def select_recent(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=max(1, days))
    recent = []
    for record in records:
        seen = parse_iso_date(str(record.get("last_seen") or record.get("first_seen") or ""))
        if seen is None or seen >= cutoff:
            recent.append(record)
    return recent


def top_counter(values: list[str], limit: int = 12) -> list[tuple[str, int]]:
    counter = Counter(value for value in values if value)
    return counter.most_common(limit)


def render_weekly_review(
    records: list[dict[str, Any]],
    profile: dict[str, Any],
    feedback: dict[str, Any] | None = None,
    days: int = 7,
    limit: int = 12,
) -> str:
    recent = select_recent(records, days)
    ranked = sorted(
        recent,
        key=lambda record: (
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(str(record.get("tier", "")), 9),
            -int(record.get("score", 0) or 0),
            str(record.get("title", "")).lower(),
        ),
    )
    must = [record for record in ranked if record.get("tier") == "Must read"]
    skim = [record for record in ranked if record.get("tier") == "Skim"]
    tags = top_counter([tag for record in recent for tag in record.get("tags", [])], 10)
    terms = top_counter([term for record in recent for term in record.get("matched_terms", [])], 12)
    alerts = top_counter([alert for record in recent for alert in record.get("alerts", [])], 10)
    noted = [record for record in ranked if feedback_note(record, feedback)]
    status_counts = Counter(reading_status(record, feedback) for record in recent)

    lines = [
        "# Weekly Literature Review",
        "",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Window: latest {days} days",
        f"- Papers considered: {len(recent)}",
        f"- Must read: {len(must)}; Skim: {len(skim)}",
        f"- Papers with personal notes: {len(noted)}",
        "",
    ]

    questions = profile.get("research_questions", [])
    if questions:
        lines.extend(["## Active Questions", ""])
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    lines.extend(["## High-Priority Reading", ""])
    if not must:
        lines.append("No Must read papers in this window.")
    for record in must[:limit]:
        lines.append(paper_line(record))
        lines.append(f"  - Status: {reading_status(record, feedback)}")
        labels = reading_labels(record, feedback)
        if labels:
            lines.append(f"  - Labels: {', '.join(labels)}")
        note = feedback_note_summary(record, feedback)
        if note:
            lines.append(f"  - Note: {note}")
    lines.append("")

    lines.extend(["## Skim Candidates", ""])
    if not skim:
        lines.append("No Skim papers in this window.")
    for record in skim[:limit]:
        lines.append(paper_line(record))
        note = feedback_note_summary(record, feedback)
        if note:
            lines.append(f"  - Note: {note}")
    lines.append("")

    lines.extend(["## Reading State", ""])
    if status_counts:
        lines.append("; ".join(f"{name}: {count}" for name, count in sorted(status_counts.items())))
    else:
        lines.append("No reading-status signals yet.")
    lines.append("")

    lines.extend(["## Personal Notes Review", ""])
    if noted:
        for record in noted[:limit]:
            lines.append(paper_line(record))
            lines.append(f"  - Status: {reading_status(record, feedback)}")
            labels = reading_labels(record, feedback)
            if labels:
                lines.append(f"  - Labels: {', '.join(labels)}")
            lines.append(f"  - Note: {feedback_note_summary(record, feedback)}")
    else:
        lines.append("No saved personal notes in this window.")
    lines.append("")

    lines.extend(["## Direction Signals", ""])
    if tags:
        lines.append("Tags: " + "; ".join(f"{name} ({count})" for name, count in tags))
    if terms:
        lines.append("Terms: " + "; ".join(f"{name} ({count})" for name, count in terms))
    if alerts:
        lines.append("Alerts: " + "; ".join(f"{name} ({count})" for name, count in alerts))
    if not (tags or terms or alerts):
        lines.append("No repeated direction signals yet.")
    lines.append("")

    lines.extend(["## Suggested Next Actions", ""])
    if must:
        lines.append("- Deep-read the top Must read papers and add notes to their paper pages.")
    if tags:
        lines.append(f"- Consider a focused search around `{tags[0][0]}` if it remains central next week.")
    if not must and skim:
        lines.append("- Lower thresholds temporarily or add a runtime boost if this week had too few direct hits.")
    if not recent:
        lines.append("- Run daily/foundation first; the weekly review needs retained papers.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"
