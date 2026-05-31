"""Rendering helpers for local library markdown outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
import re
from pathlib import Path
from typing import Any

from ..ranking import aggregate_score_breakdown, human_score_component_lines, paper_score_components
from .status import feedback_note, priority_override, reading_labels, reading_status, record_source_types
from .store import paper_directions


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_score_components_lines(components: list[dict[str, Any]]) -> list[str]:
    if not components:
        return ["score_components: []"]

    lines: list[str] = ["score_components:"]
    for component in components:
        lines.extend(
            [
                "  -",
                f"    name: {_yaml_scalar(component.get('name', ''))}",
                f"    value: {_yaml_scalar(component.get('value', 0.0))}",
                f"    explanation: {_yaml_scalar(component.get('explanation', ''))}",
                f"    evidence_field: {_yaml_scalar(component.get('evidence_field', ''))}",
                "    matched_terms:",
            ]
        )
        for term in component.get("matched_terms", []):
            lines.append(f"      - {_yaml_scalar(term)}")
    return lines


def _paper_metadata_from_authors_source(authors_source: str) -> dict[str, str | None]:
    cleaned = re.sub(r"\s+[-–—]\s+", " - ", authors_source or "").strip()
    parts = [part.strip() for part in cleaned.split(" - ") if part.strip()]
    authors = parts[0] if parts else None
    venue = parts[1] if len(parts) >= 2 else None
    year = None
    if len(parts) >= 3:
        year = parts[2]
    if not year:
        year_match = re.search(r"\b(19|20)\d{2}\b", authors_source or "")
        year = year_match.group(0) if year_match else None
    doi = None
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", authors_source or "")
    if doi_match:
        doi = doi_match.group(0)

    return {
        "authors": authors,
        "venue": venue,
        "year": year,
        "doi": doi,
    }


def _paper_source_history_lines(paper: Any, feedback: dict[str, Any] | None = None) -> list[str]:
    lines = [
        f"- First seen: {paper.first_seen or 'unknown'}",
        f"- Last seen: {paper.last_seen or 'unknown'}",
        f"- Occurrences: {paper.occurrences}",
    ]
    if getattr(paper, "alerts", []):
        lines.append("- Alerts:")
        lines.extend(f"  - {alert}" for alert in paper.alerts)

    if not isinstance(feedback, dict):
        return lines
    item = feedback.get("papers", {}).get(str(paper.id), {})
    if not isinstance(item, dict):
        return lines
    updated_at = item.get("updated_at")
    if updated_at:
        lines.append(f"- Last feedback update: {updated_at}")
    return lines


def metadata_lines(paper: Any) -> list[str]:
    """Render metadata block for a single paper note."""

    lines: list[str] = []
    metadata = getattr(paper, "metadata", None)
    if not isinstance(metadata, dict):
        return lines
    zotero = metadata.get("zotero")
    full_text = metadata.get("full_text")
    openalex = metadata.get("openalex")
    crossref = metadata.get("crossref")
    if isinstance(zotero, dict):
        lines.extend(
            [
                "## Zotero",
                "",
                f"- Citation key: {zotero.get('citation_key', '')}",
                f"- Item key: {zotero.get('item_key', '')}",
                f"- DOI: {zotero.get('doi', '')}",
            ]
        )
        for path in zotero.get("pdf_paths", []):
            lines.append(f"- Local PDF: {path}")
        lines.append("")
    if isinstance(full_text, dict):
        lines.extend(
            [
                "## Full Text",
                "",
                f"- Source: {full_text.get('source', '')}",
                f"- PDF URL: {full_text.get('pdf_url', '')}",
            ]
        )
        for path in full_text.get("pdf_paths", []):
            lines.append(f"- Local PDF: {path}")
        lines.append("")
    if isinstance(openalex, dict):
        lines.extend(
            [
                "## OpenAlex",
                "",
                f"- Year: {openalex.get('publication_year', '')}",
                f"- Cited by: {openalex.get('cited_by_count', '')}",
                f"- Source: {openalex.get('source', '')}",
                f"- DOI: {openalex.get('doi', '')}",
                f"- PDF: {openalex.get('pdf_url', '')}",
                "",
            ]
        )
    if isinstance(crossref, dict):
        lines.extend(
            [
                "## Crossref",
                "",
                f"- DOI: {crossref.get('doi', '')}",
                f"- Journal/source: {crossref.get('container_title', '')}",
                f"- Publisher: {crossref.get('publisher', '')}",
                f"- Referenced by: {crossref.get('is_referenced_by_count', '')}",
                "",
            ]
        )
    return lines


def write_kb_paper_pages(
    kb_dir: Path,
    papers: list[Any],
    feedback: dict[str, Any] | None = None,
    paper_evidence_text_fn: Any | None = None,
) -> None:
    """Write one markdown note per paper under kb_dir/papers."""

    if not isinstance(feedback, dict):
        feedback = {"version": 1, "papers": {}, "terms": []}

    if paper_evidence_text_fn is None:
        def paper_evidence_text_fn(local_paper: Any, _kb: Path | None = None) -> str:
            return "metadata-only (unknown) - No evidence helper available"

    paper_dir = kb_dir / "papers"
    paper_dir.mkdir(parents=True, exist_ok=True)
    for paper in papers:
        record = asdict(paper)
        labels = reading_labels(record, feedback)
        status = reading_status(record, feedback)
        priority = priority_override(record, feedback)
        note = feedback_note(record, feedback, limit=3000)
        source_types = record_source_types(record)
        components = paper_score_components(paper)
        metadata = _paper_metadata_from_authors_source(str(getattr(paper, "authors_source", "")))
        feedback_item = feedback.get("papers", {}).get(str(paper.id), {})
        if not isinstance(feedback_item, dict):
            feedback_item = {}
        feedback_status = str(feedback_item.get("status", "neutral") or "neutral")
        frontmatter = [
            "---",
            f"paper_id: {_yaml_scalar(getattr(paper, 'id', ''))}",
            f"title: {_yaml_scalar(getattr(paper, 'title', ''))}",
            f"url: {_yaml_scalar(getattr(paper, 'url', ''))}",
            f"tier: {_yaml_scalar(getattr(paper, 'tier', ''))}",
            f"score: {_yaml_scalar(getattr(paper, 'score', 0))}",
            f"first_seen: {_yaml_scalar(getattr(paper, 'first_seen', ''))}",
            f"last_seen: {_yaml_scalar(getattr(paper, 'last_seen', ''))}",
            f"reading_status: {_yaml_scalar(status)}",
            f"feedback_status: {_yaml_scalar(feedback_status)}",
            f"priority_override: {_yaml_scalar(priority)}",
            "tags:",
            *[f"  - {_yaml_scalar(tag)}" for tag in sorted(set(getattr(paper, "tags", [])))],
            *_yaml_score_components_lines(components),
            "source_types:",
            *[f"  - {_yaml_scalar(source_type)}" for source_type in source_types],
            "---",
            "",
        ]
        breakdown_lines = [f"  - {component.get('name', '')}: {float(component.get('value', 0.0)):+.2f}" for component in components]
        lines = [
            *frontmatter,
            f"# {getattr(paper, 'title', 'Untitled')}",
            "",
            f"- ID: {getattr(paper, 'id', '')}",
            f"- Authors: {metadata['authors'] or 'unknown'}",
            f"- Venue: {metadata['venue'] or 'unknown'}",
            f"- Year: {metadata['year'] or 'unknown'}",
            f"- DOI: {metadata['doi'] or 'unknown'}",
            f"- Tier: {getattr(paper, 'tier', '')}",
            f"- Score: {getattr(paper, 'score', 0)}",
            f"- Source: {getattr(paper, 'authors_source', '')}",
            f"- Evidence: {paper_evidence_text_fn(paper, kb_dir)}",
            f"- First seen: {getattr(paper, 'first_seen', '')}",
            f"- Last seen: {getattr(paper, 'last_seen', '')}",
            f"- Directions: {', '.join(paper_directions(paper))}",
            f"- Matched: {', '.join(getattr(paper, 'matched_terms', []))}",
            f"- Reading status: {status}",
            f"- Labels: {', '.join(labels) if labels else 'none'}",
            "",
            "## Why selected",
            "",
            "- Score breakdown:",
            *breakdown_lines,
            *human_score_component_lines(
                paper,
                include_zero=True,
            ),
            "",
            "## Snippet",
            "",
            getattr(paper, "snippet", "") or "No snippet available.",
            "",
            "## Why It Ranked",
        ]
        lines.extend(f"- {reason}" for reason in getattr(paper, "reasons", [])[:8])
        lines.append("")
        lines.extend(metadata_lines(paper))
        lines.append("")
        lines.append("## Source history")
        lines.extend(_paper_source_history_lines(paper, feedback))
        lines.append("")
        if note:
            lines.extend(
                [
                    "## Saved Feedback",
                    "",
                    note,
                    "",
                ]
            )
        lines.extend(["## Notes", "", "- ", ""])
        (paper_dir / f"{paper.id}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_search_index(
    kb_dir: Path,
    papers: list[Any],
    feedback: dict[str, Any] | None = None,
) -> None:
    if feedback is None:
        feedback = {"version": 1, "papers": {}, "terms": []}
    feedback_papers = feedback.get("papers", {}) if isinstance(feedback, dict) else {}
    search_records: list[dict[str, Any]] = []
    for paper in sorted(papers, key=lambda item: (-getattr(item, "score", 0), str(getattr(item, "title", "")).lower())):
        record = feedback_papers.get(str(paper.id), {}) if isinstance(feedback_papers, dict) else {}
        if not isinstance(record, dict):
            record = {}
        paper_record = asdict(paper)
        components = paper_score_components(paper)
        score_breakdown = aggregate_score_breakdown(components)
        search_records.append(
            {
                "id": paper.id,
                "title": paper.title,
                "tier": paper.tier,
                "score": paper.score,
                "url": paper.url,
                "authors_source": paper.authors_source,
                "snippet": paper.snippet,
                "tags": list(getattr(paper, "tags", [])),
                "matched_terms": list(getattr(paper, "matched_terms", [])),
                "first_seen": paper.first_seen,
                "last_seen": paper.last_seen,
                "directions": paper_directions(paper),
                "score_components": components,
                "score_breakdown": score_breakdown,
                "feedback_status": str(record.get("status", "neutral") or "neutral"),
                "reading_status": str(record.get("reading_status", "unread") or "unread"),
                "priority_override": priority_override(paper_record, feedback),
                "labels": list(record.get("labels", [])) if isinstance(record.get("labels", []), list) else [],
            }
        )
    (kb_dir / "search_index.json").write_text(
        json.dumps(search_records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
