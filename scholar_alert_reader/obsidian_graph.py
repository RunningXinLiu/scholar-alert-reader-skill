"""Private Obsidian graph export for the paper universe.

This module intentionally writes generated notes into a dedicated folder. It
uses wikilinks only for this opt-in graph export; the default clean Obsidian
export remains link-light to avoid polluting a user's personal graph.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .duplicates import find_duplicate_candidates


UNIVERSE_IMPORT_MODE = "paper_universe_graph"
RESEARCH_IMPORT_MODE = "research_knowledge_graph"
GRAPH_IMPORT_MODE = UNIVERSE_IMPORT_MODE
GRAPH_IMPORT_MODES = {UNIVERSE_IMPORT_MODE, RESEARCH_IMPORT_MODE}
GRAPH_MANIFEST = ".scholar_alert_reader_obsidian_graph_manifest.json"


@dataclass
class ObsidianGraphExportResult:
    export_dir: Path
    paper_notes: int
    collection_notes: int
    topic_notes: int
    venue_notes: int
    author_notes: int
    possible_overlaps: int
    manifest: Path
    index: Path
    overlap_report: Path
    graph_mode: str = "universe"
    concept_notes: int = 0


def stable_suffix(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:length]


def safe_name(value: Any, max_len: int = 96) -> str:
    text = " ".join(str(value or "").split())
    text = re.sub(r"[\\/:*?\"<>|\[\]#^]+", " ", text)
    text = " ".join(text.split()).strip(" .")
    return (text[:max_len].strip() or "Untitled")


def yaml_scalar(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return json.dumps(text, ensure_ascii=False)


def yaml_list(values: list[Any]) -> str:
    cleaned = [" ".join(str(value).split()) for value in values if str(value).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def paper_id(record: dict[str, Any]) -> str:
    value = str(record.get("paper_id") or record.get("id") or "").strip()
    if value:
        return value
    return stable_suffix(str(record.get("title", "Untitled")), 12)


def paper_title(record: dict[str, Any]) -> str:
    return " ".join(str(record.get("title") or "Untitled").split())


def paper_note_name(record: dict[str, Any]) -> str:
    return f"Paper - {safe_name(paper_title(record), 86)} [{paper_id(record)}]"


def collection_note_name(collection: str) -> str:
    return f"Collection - {safe_name(collection, 82)} [{stable_suffix(collection)}]"


def topic_note_name(topic: str) -> str:
    return f"Topic - {safe_name(topic, 90)} [{stable_suffix(topic.lower())}]"


def concept_note_name(concept: dict[str, Any]) -> str:
    concept_id = str(concept.get("id") or concept.get("name") or "").strip()
    name = str(concept.get("name") or concept_id or "Concept").strip()
    suffix = concept_id or stable_suffix(name.lower())
    return f"Concept - {safe_name(name, 86)} [{safe_name(suffix, 24)}]"


def venue_note_name(venue: str) -> str:
    return f"Venue - {safe_name(venue, 90)} [{stable_suffix(venue.lower())}]"


def author_note_name(author: str) -> str:
    return f"Author - {safe_name(author, 90)} [{stable_suffix(author.lower())}]"


def wikilink(note_name: str, alias: str | None = None) -> str:
    if alias and alias != note_name:
        return f"[[{note_name}|{alias}]]"
    return f"[[{note_name}]]"


def clean_topics(record: dict[str, Any], limit: int = 8) -> list[str]:
    skip = {
        "adaptive",
        "feedback",
        "semantic",
        "region",
        "method",
        "dataset",
        "watchlist",
        "metadata-only",
        "metadata-enriched",
        "pdf-link-ready",
        "local-pdf-ready",
        "full-text-backed",
    }
    topics: list[str] = []
    for value in coerce_list(record.get("tags")):
        topic = str(value).strip()
        if not topic or topic.lower() in skip:
            continue
        if topic not in topics:
            topics.append(topic)
    for value in coerce_list(record.get("matched_terms")):
        topic = str(value).strip()
        if not topic:
            continue
        lowered = topic.lower()
        if lowered.startswith(("user:", "similar:", "dissimilar:")) or lowered.startswith("user:-"):
            continue
        if lowered in skip:
            continue
        if ":" in topic or len(topic) > 80:
            continue
        if topic not in topics:
            topics.append(topic)
        if len(topics) >= limit:
            break
    return topics[:limit]


def record_venue(record: dict[str, Any]) -> str:
    for field in ["venue", "journal", "source", "publication"]:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return ""


def record_year(record: dict[str, Any]) -> str:
    value = record.get("year")
    if isinstance(value, int):
        return str(value)
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return match.group(0) if match else ""


def record_authors(record: dict[str, Any]) -> list[str]:
    authors = coerce_list(record.get("authors"))
    if not authors:
        source = str(record.get("authors_source") or "")
        if " - " in source:
            source = source.split(" - ", 1)[0]
        authors = [part.strip() for part in source.split(",")]
    return [str(author).strip() for author in authors if str(author).strip()]


def local_pdf_links(record: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for path in coerce_list(record.get("pdf_paths")):
        text = str(path).strip()
        if not text:
            continue
        links.append(f"[PDF]({Path(text).as_uri()})" if text.startswith("/") else text)
    return links


def is_generated_graph_file(path: Path) -> bool:
    if path.name == GRAPH_MANIFEST:
        return True
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:800]
    except OSError:
        return False
    if "source_tool: scholar-alert-reader" not in head:
        return False
    return any(f"obsidian_import: {mode}" in head for mode in GRAPH_IMPORT_MODES)


def prune_previous_export(export_dir: Path) -> int:
    manifest = export_dir / GRAPH_MANIFEST
    if not manifest.exists():
        return 0
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if data.get("marker") != "scholar-alert-reader:obsidian-graph-generated":
        return 0
    removed = 0
    for rel in data.get("files", []):
        rel_text = str(rel)
        if not rel_text or rel_text.startswith("/") or ".." in Path(rel_text).parts:
            continue
        target = export_dir / rel_text
        if target.exists() and target.is_file() and is_generated_graph_file(target):
            target.unlink()
            removed += 1
    return removed


def write_note(path: Path, content: str, generated_files: list[Path], export_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    generated_files.append(path.relative_to(export_dir))


def paper_frontmatter(
    record: dict[str, Any],
    topics: list[str],
    collections: list[str],
    *,
    import_mode: str = UNIVERSE_IMPORT_MODE,
    concepts: list[str] | None = None,
) -> list[str]:
    concept_values = concepts or []
    return [
        "---",
        "type: paper",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {import_mode}",
        f"paper_id: {yaml_scalar(paper_id(record))}",
        f"title: {yaml_scalar(paper_title(record))}",
        f"year: {yaml_scalar(record_year(record))}",
        f"venue: {yaml_scalar(record_venue(record))}",
        f"tier: {yaml_scalar(record.get('tier', ''))}",
        f"score: {record.get('score', 0) or 0}",
        f"doi: {yaml_scalar(record.get('doi', ''))}",
        f"url: {yaml_scalar(record.get('url', ''))}",
        f"source_types: {yaml_list(coerce_list(record.get('source_types')))}",
        f"zotero_collections: {yaml_list(collections)}",
        f"zotero_collections_raw: {yaml_list(collections)}",
        f"graph_topics: {yaml_list(topics)}",
        f"graph_concepts: {yaml_list(concept_values)}",
        f"tags: {yaml_list(coerce_list(record.get('tags')))}",
        "---",
        "",
    ]


def render_paper_note(
    record: dict[str, Any],
    topics: list[str],
    collections: list[str],
    include_authors: bool,
) -> str:
    title = paper_title(record)
    venue = record_venue(record)
    year = record_year(record)
    pdfs = local_pdf_links(record)
    lines = paper_frontmatter(record, topics, collections) + [
        f"# {title}",
        "",
        "## Graph Links",
        "",
    ]
    if collections:
        lines.append("- Collections: " + ", ".join(wikilink(collection_note_name(item), item) for item in collections))
    if topics:
        lines.append("- Topics: " + ", ".join(wikilink(topic_note_name(item), item) for item in topics))
    if venue:
        lines.append(f"- Venue: {wikilink(venue_note_name(venue), venue)}")
    authors = record_authors(record)
    if include_authors and authors:
        lines.append("- Authors: " + ", ".join(wikilink(author_note_name(item), item) for item in authors[:8]))
    lines.extend(
        [
            "",
            "## Metadata",
            "",
            f"- Year: {year or 'unknown'}",
            f"- Venue: {venue or 'unknown'}",
            f"- DOI: {record.get('doi') or 'not found'}",
            f"- URL: {record.get('url') or 'not found'}",
            f"- Sources: {', '.join(str(item) for item in coerce_list(record.get('source_types'))) or 'unknown'}",
            f"- Tier / score: {record.get('tier', 'unknown')} / {record.get('score', 0)}",
            f"- Local PDF: {', '.join(pdfs) if pdfs else 'not linked'}",
            "",
            "## Abstract",
            "",
            str(record.get("abstract") or record.get("snippet") or "No abstract/snippet available."),
            "",
            "## My Notes",
            "",
            "- ",
        ]
    )
    return "\n".join(lines)


def render_node_note(
    *,
    title: str,
    node_type: str,
    node_id: str,
    description: str,
    papers: list[dict[str, Any]],
    max_papers: int,
    import_mode: str = UNIVERSE_IMPORT_MODE,
) -> str:
    lines = [
        "---",
        f"type: {node_type}",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {import_mode}",
        f"node_id: {yaml_scalar(node_id)}",
        f"title: {yaml_scalar(title)}",
        f"paper_count: {len(papers)}",
        "---",
        "",
        f"# {title}",
        "",
        description,
        "",
        "## Papers",
        "",
    ]
    for record in sorted(papers, key=lambda item: (-(float(item.get("score", 0) or 0)), paper_title(item).lower()))[:max_papers]:
        year = record_year(record)
        suffix = f" ({year})" if year else ""
        lines.append(f"- {wikilink(paper_note_name(record), paper_title(record))}{suffix} · {record.get('tier', '')} · score {record.get('score', 0)}")
    if len(papers) > max_papers:
        lines.append(f"- ... {len(papers) - max_papers} more papers omitted from this node note.")
    return "\n".join(lines)


def possible_zotero_scholar_overlaps(records: list[dict[str, Any]], threshold: float = 0.82, limit: int = 120) -> list[dict[str, Any]]:
    candidates = find_duplicate_candidates(records, title_threshold=threshold, year_tolerance=2, limit=limit)
    return [
        {
            "score": item["evidence"]["score"],
            "confidence": item["confidence"],
            "evidence": item["evidence"],
            "scholar": item["left"],
            "zotero": item["right"],
        }
        for item in candidates
    ]


def render_overlap_report(candidates: list[dict[str, Any]]) -> str:
    lines = [
        "---",
        "type: overlap_report",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {UNIVERSE_IMPORT_MODE}",
        "---",
        "",
        "# Possible Scholar Alert / Zotero Overlaps",
        "",
        "This is a review report only. It does not merge records automatically.",
        "",
    ]
    if not candidates:
        lines.append("- No high-confidence title overlaps found.")
        return "\n".join(lines)
    lines.extend(["| Similarity | Confidence | Scholar Alert paper | Zotero paper | Evidence |", "|---:|---|---|---|---|"])
    for item in candidates:
        scholar = item["scholar"]
        zotero = item["zotero"]
        evidence = item.get("evidence", {})
        details: list[str] = []
        if evidence.get("first_author_match") is True:
            details.append("first author matches")
        if evidence.get("year_match") is True:
            details.append("year compatible")
        if evidence.get("doi_match"):
            details.append("DOI matches")
        lines.append(
            f"| {item['score']:.3f} | {item.get('confidence', 'review')} | {wikilink(paper_note_name(scholar), paper_title(scholar))} | {wikilink(paper_note_name(zotero), paper_title(zotero))} | {', '.join(details) or 'title only'} |"
        )
    return "\n".join(lines)


def render_index(
    records: list[dict[str, Any]],
    collection_counts: Counter[str],
    topic_counts: Counter[str],
    venue_counts: Counter[str],
    include_authors: bool,
    author_counts: Counter[str],
    possible_overlaps: int,
    import_mode: str = UNIVERSE_IMPORT_MODE,
    title: str = "Paper Universe Graph",
) -> str:
    source_counts = Counter()
    for record in records:
        source_counts.update(str(item) for item in coerce_list(record.get("source_types")) if str(item).strip())
    lines = [
        "---",
        "type: literature_graph_index",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {import_mode}",
        f"paper_count: {len(records)}",
        "---",
        "",
        f"# {title}",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers: {len(records)}",
        f"- Collections: {len(collection_counts)}",
        f"- Topics: {len(topic_counts)}",
        f"- Venues: {len(venue_counts)}",
        f"- Authors: {len(author_counts) if include_authors else 0}",
        f"- Possible Scholar Alert / Zotero overlaps to review: {possible_overlaps}",
        "",
        "## Source Mix",
        "",
    ]
    for source, count in source_counts.most_common():
        lines.append(f"- {source}: {count}")
    lines.extend(["", "## Entry Points", ""])
    if collection_counts:
        lines.append("### Top Collections")
        for collection, count in collection_counts.most_common(20):
            lines.append(f"- {wikilink(collection_note_name(collection), collection)} · {count}")
        lines.append("")
    if topic_counts:
        lines.append("### Top Topics")
        for topic, count in topic_counts.most_common(20):
            lines.append(f"- {wikilink(topic_note_name(topic), topic)} · {count}")
        lines.append("")
    if venue_counts:
        lines.append("### Top Venues")
        for venue, count in venue_counts.most_common(20):
            lines.append(f"- {wikilink(venue_note_name(venue), venue)} · {count}")
        lines.append("")
    lines.append(f"- {wikilink('Possible Scholar Zotero Overlaps', 'Possible overlaps report')}")
    return "\n".join(lines)


def load_taxonomy(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    path = path.expanduser()
    if not path.exists():
        raise SystemExit(f"Cannot find knowledge graph taxonomy: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Taxonomy must be a JSON object: {path}")
    return data


def record_search_text(record: dict[str, Any]) -> str:
    parts: list[str] = [
        paper_title(record),
        str(record.get("abstract") or ""),
        str(record.get("snippet") or ""),
        str(record.get("venue") or ""),
        " ".join(str(item) for item in coerce_list(record.get("tags"))),
        " ".join(str(item) for item in coerce_list(record.get("matched_terms"))),
        " ".join(str(item) for item in coerce_list(record.get("zotero_collections"))),
    ]
    return " ".join(parts).lower()


def taxonomy_concepts(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    concepts = taxonomy.get("concepts", [])
    if not isinstance(concepts, list):
        return []
    output: list[dict[str, Any]] = []
    for item in concepts:
        if isinstance(item, dict) and (item.get("name") or item.get("id")):
            output.append(item)
    return output


def concept_terms(concept: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ["name", "aliases", "terms", "keywords"]:
        for value in coerce_list(concept.get(field)):
            text_value = str(value).strip().lower()
            if len(text_value) >= 3 and text_value not in values:
                values.append(text_value)
    return values


def collection_terms(concept: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ["collections", "zotero_collections", "collection_aliases"]:
        for value in coerce_list(concept.get(field)):
            text_value = str(value).strip().lower()
            if text_value and text_value not in values:
                values.append(text_value)
    return values


def taxonomy_excluded(record: dict[str, Any], taxonomy: dict[str, Any]) -> bool:
    text_blob = record_search_text(record)
    for term in coerce_list(taxonomy.get("exclude_terms")):
        cleaned = str(term).strip().lower()
        if cleaned and cleaned in text_blob:
            return True
    return False


def match_concepts(record: dict[str, Any], concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text_blob = record_search_text(record)
    collection_blob = " | ".join(str(item).lower() for item in coerce_list(record.get("zotero_collections")))
    matched: list[dict[str, Any]] = []
    for concept in concepts:
        term_hit = any(term in text_blob for term in concept_terms(concept))
        collection_hit = any(term in collection_blob for term in collection_terms(concept))
        if term_hit or collection_hit:
            matched.append(concept)
    return matched


def research_record_priority(record: dict[str, Any]) -> tuple[int, float, str]:
    status = str(record.get("feedback_status", "")).lower()
    reading_status = str(record.get("reading_status", "")).lower()
    tier = str(record.get("tier", "")).lower()
    if status == "interested":
        priority = 0
    elif reading_status in {"reading", "read", "must-cite", "method-reference", "method-ref"}:
        priority = 1
    elif tier == "must read":
        priority = 2
    elif tier == "skim":
        priority = 3
    else:
        priority = 4
    try:
        score = float(record.get("score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
    return (priority, -score, paper_title(record).lower())


def research_records(
    records: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    *,
    min_concepts: int,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    concepts = taxonomy_concepts(taxonomy)
    if not concepts:
        raise SystemExit("Research graph mode needs a taxonomy with at least one concept.")
    selected: list[dict[str, Any]] = []
    paper_concepts: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if taxonomy_excluded(record, taxonomy):
            continue
        matched = match_concepts(record, concepts)
        if len(matched) < min_concepts:
            continue
        selected.append(record)
        paper_concepts[paper_id(record)] = matched
    selected.sort(key=research_record_priority)
    return selected, paper_concepts


def render_research_paper_note(record: dict[str, Any], concepts: list[dict[str, Any]]) -> str:
    title = paper_title(record)
    venue = record_venue(record)
    year = record_year(record)
    collections = [str(item) for item in coerce_list(record.get("zotero_collections")) if str(item).strip()]
    concept_names = [str(concept.get("name") or concept.get("id")) for concept in concepts]
    pdfs = local_pdf_links(record)
    lines = paper_frontmatter(
        record,
        [],
        collections,
        import_mode=RESEARCH_IMPORT_MODE,
        concepts=concept_names,
    ) + [
        f"# {title}",
        "",
        "## Knowledge Links",
        "",
        "- Concepts: " + ", ".join(wikilink(concept_note_name(concept), str(concept.get("name") or concept.get("id"))) for concept in concepts),
        "",
        "## Metadata",
        "",
        f"- Year: {year or 'unknown'}",
        f"- Venue: {venue or 'unknown'}",
        f"- DOI: {record.get('doi') or 'not found'}",
        f"- URL: {record.get('url') or 'not found'}",
        f"- Sources: {', '.join(str(item) for item in coerce_list(record.get('source_types'))) or 'unknown'}",
        f"- Tier / score: {record.get('tier', 'unknown')} / {record.get('score', 0)}",
        f"- Local PDF: {', '.join(pdfs) if pdfs else 'not linked'}",
        "",
        "### Zotero provenance",
        "",
    ]
    if collections:
        lines.extend(f"- `{collection}`" for collection in collections)
    else:
        lines.append("- not linked to a Zotero collection")
    lines.extend(
        [
            "",
            "## Abstract",
            "",
            str(record.get("abstract") or record.get("snippet") or "No abstract/snippet available."),
            "",
            "## My Notes",
            "",
            "- ",
        ]
    )
    return "\n".join(lines)


def render_research_concept_note(concept: dict[str, Any], papers: list[dict[str, Any]], max_papers: int) -> str:
    name = str(concept.get("name") or concept.get("id") or "Concept")
    concept_type = str(concept.get("type") or "concept")
    description = str(concept.get("description") or "Curated research concept from the local taxonomy.")
    aliases = [str(item) for item in coerce_list(concept.get("aliases")) if str(item).strip()]
    lines = [
        "---",
        "type: research_concept",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {RESEARCH_IMPORT_MODE}",
        f"concept_id: {yaml_scalar(concept.get('id') or name)}",
        f"concept_type: {yaml_scalar(concept_type)}",
        f"title: {yaml_scalar(name)}",
        f"aliases: {yaml_list(aliases)}",
        f"paper_count: {len(papers)}",
        "---",
        "",
        f"# {name}",
        "",
        f"- Type: `{concept_type}`",
        f"- Papers: {len(papers)}",
        "",
        "## Scope",
        "",
        description,
        "",
        "## Papers",
        "",
    ]
    for record in sorted(papers, key=research_record_priority)[:max_papers]:
        year = record_year(record)
        suffix = f" ({year})" if year else ""
        lines.append(f"- {wikilink(paper_note_name(record), paper_title(record))}{suffix} · {record.get('tier', '')} · score {record.get('score', 0)}")
    if len(papers) > max_papers:
        lines.append(f"- ... {len(papers) - max_papers} more papers omitted from this concept note.")
    return "\n".join(lines)


def render_research_index(records: list[dict[str, Any]], concept_papers: dict[str, list[dict[str, Any]]], taxonomy_path: Path | None) -> str:
    source_counts = Counter()
    for record in records:
        source_counts.update(str(item) for item in coerce_list(record.get("source_types")) if str(item).strip())
    lines = [
        "---",
        "type: research_graph_index",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {RESEARCH_IMPORT_MODE}",
        f"paper_count: {len(records)}",
        "---",
        "",
        "# Research Knowledge Graph",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers: {len(records)}",
        f"- Concepts: {len(concept_papers)}",
        f"- Taxonomy: `{taxonomy_path}`" if taxonomy_path else "- Taxonomy: inline/default",
        "",
        "This graph is concept-first. Zotero subcollections are preserved as provenance in paper frontmatter, but they are not graph nodes.",
        "",
        "## Source Mix",
        "",
    ]
    for source, count in source_counts.most_common():
        lines.append(f"- {source}: {count}")
    lines.extend(["", "## Concepts", ""])
    for note_name, papers in sorted(concept_papers.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        lines.append(f"- {wikilink(note_name)} · {len(papers)}")
    return "\n".join(lines)


def export_research_graph(
    records: list[dict[str, Any]],
    export_dir: Path,
    *,
    taxonomy: dict[str, Any],
    taxonomy_path: Path | None = None,
    limit: int = 0,
    min_concepts: int = 1,
    max_papers_per_node: int = 80,
    prune: bool = True,
) -> ObsidianGraphExportResult:
    export_dir = export_dir.expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    if prune:
        prune_previous_export(export_dir)
    selected, paper_concepts = research_records(records, taxonomy, min_concepts=min_concepts)
    if limit > 0:
        selected = selected[:limit]
    selected_ids = {paper_id(record) for record in selected}
    paper_concepts = {pid: concepts for pid, concepts in paper_concepts.items() if pid in selected_ids}

    concept_papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    concept_lookup: dict[str, dict[str, Any]] = {}
    for record in selected:
        for concept in paper_concepts.get(paper_id(record), []):
            note_name = concept_note_name(concept)
            concept_papers[note_name].append(record)
            concept_lookup[note_name] = concept

    generated_files: list[Path] = []
    for record in selected:
        path = export_dir / "01_Papers" / f"{paper_note_name(record)}.md"
        write_note(path, render_research_paper_note(record, paper_concepts.get(paper_id(record), [])), generated_files, export_dir)

    for note_name, papers in concept_papers.items():
        path = export_dir / "02_Concepts" / f"{note_name}.md"
        write_note(
            path,
            render_research_concept_note(concept_lookup[note_name], papers, max_papers_per_node),
            generated_files,
            export_dir,
        )

    index_path = export_dir / "00_Index" / "Research Knowledge Graph.md"
    write_note(index_path, render_research_index(selected, concept_papers, taxonomy_path), generated_files, export_dir)
    overlap_path = export_dir / "00_Index" / "Possible Scholar Zotero Overlaps.md"
    overlap_candidates = possible_zotero_scholar_overlaps(selected)
    write_note(overlap_path, render_overlap_report(overlap_candidates).replace(UNIVERSE_IMPORT_MODE, RESEARCH_IMPORT_MODE), generated_files, export_dir)

    manifest = export_dir / GRAPH_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "marker": "scholar-alert-reader:obsidian-graph-generated",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "files": [str(path) for path in generated_files],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ObsidianGraphExportResult(
        export_dir=export_dir,
        paper_notes=len(selected),
        collection_notes=0,
        topic_notes=0,
        venue_notes=0,
        author_notes=0,
        possible_overlaps=len(overlap_candidates),
        manifest=manifest,
        index=index_path,
        overlap_report=overlap_path,
        graph_mode="research",
        concept_notes=len(concept_papers),
    )


def export_obsidian_graph(
    records: list[dict[str, Any]],
    export_dir: Path,
    *,
    graph_mode: str = "universe",
    taxonomy: dict[str, Any] | None = None,
    taxonomy_path: Path | None = None,
    limit: int = 0,
    include_authors: bool = False,
    author_limit: int = 300,
    max_papers_per_node: int = 80,
    min_concepts: int = 1,
    prune: bool = True,
) -> ObsidianGraphExportResult:
    graph_mode = (graph_mode or "universe").strip().lower()
    if graph_mode == "research":
        return export_research_graph(
            records,
            export_dir,
            taxonomy=taxonomy or {},
            taxonomy_path=taxonomy_path,
            limit=limit,
            min_concepts=min_concepts,
            max_papers_per_node=max_papers_per_node,
            prune=prune,
        )
    if graph_mode != "universe":
        raise SystemExit("Unsupported graph mode. Use 'universe' or 'research'.")

    export_dir = export_dir.expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    if prune:
        prune_previous_export(export_dir)
    records = list(records)
    records.sort(key=lambda item: (-(float(item.get("score", 0) or 0)), paper_title(item).lower()))
    if limit > 0:
        records = records[:limit]

    collection_papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    topic_papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    venue_papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    author_papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    paper_topics: dict[str, list[str]] = {}
    paper_collections: dict[str, list[str]] = {}

    for record in records:
        pid = paper_id(record)
        collections = [str(item) for item in coerce_list(record.get("zotero_collections")) if str(item).strip()]
        topics = clean_topics(record)
        paper_topics[pid] = topics
        paper_collections[pid] = collections
        for collection in collections:
            collection_papers[collection].append(record)
        for topic in topics:
            topic_papers[topic].append(record)
        venue = record_venue(record)
        if venue:
            venue_papers[venue].append(record)
        if include_authors:
            for author in record_authors(record)[:8]:
                author_papers[author].append(record)

    if include_authors and author_limit > 0:
        keep_authors = {author for author, _ in Counter({key: len(value) for key, value in author_papers.items()}).most_common(author_limit)}
        author_papers = {key: value for key, value in author_papers.items() if key in keep_authors}

    generated_files: list[Path] = []
    for record in records:
        path = export_dir / "01_Papers" / f"{paper_note_name(record)}.md"
        write_note(path, render_paper_note(record, paper_topics[paper_id(record)], paper_collections[paper_id(record)], include_authors), generated_files, export_dir)

    for collection, papers in collection_papers.items():
        path = export_dir / "02_Collections" / f"{collection_note_name(collection)}.md"
        write_note(
            path,
            render_node_note(title=collection, node_type="literature_collection", node_id=collection, description="Generated from Zotero collection/subcollection membership.", papers=papers, max_papers=max_papers_per_node),
            generated_files,
            export_dir,
        )

    for topic, papers in topic_papers.items():
        path = export_dir / "03_Topics" / f"{topic_note_name(topic)}.md"
        write_note(
            path,
            render_node_note(title=topic, node_type="literature_topic", node_id=topic, description="Generated from profile tags and clean matched terms.", papers=papers, max_papers=max_papers_per_node),
            generated_files,
            export_dir,
        )

    for venue, papers in venue_papers.items():
        path = export_dir / "04_Venues" / f"{venue_note_name(venue)}.md"
        write_note(
            path,
            render_node_note(title=venue, node_type="literature_venue", node_id=venue, description="Generated from venue/journal metadata.", papers=papers, max_papers=max_papers_per_node),
            generated_files,
            export_dir,
        )

    if include_authors:
        for author, papers in author_papers.items():
            path = export_dir / "05_Authors" / f"{author_note_name(author)}.md"
            write_note(
                path,
                render_node_note(title=author, node_type="literature_author", node_id=author, description="Generated from bibliography author metadata.", papers=papers, max_papers=max_papers_per_node),
                generated_files,
                export_dir,
            )

    overlap_candidates = possible_zotero_scholar_overlaps(records)
    overlap_path = export_dir / "00_Index" / "Possible Scholar Zotero Overlaps.md"
    write_note(overlap_path, render_overlap_report(overlap_candidates), generated_files, export_dir)

    index_path = export_dir / "00_Index" / "Paper Universe Graph.md"
    write_note(
        index_path,
        render_index(
            records,
            Counter({key: len(value) for key, value in collection_papers.items()}),
            Counter({key: len(value) for key, value in topic_papers.items()}),
            Counter({key: len(value) for key, value in venue_papers.items()}),
            include_authors,
            Counter({key: len(value) for key, value in author_papers.items()}),
            len(overlap_candidates),
        ),
        generated_files,
        export_dir,
    )

    manifest = export_dir / GRAPH_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "marker": "scholar-alert-reader:obsidian-graph-generated",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "files": [str(path) for path in generated_files],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ObsidianGraphExportResult(
        export_dir=export_dir,
        paper_notes=len(records),
        collection_notes=len(collection_papers),
        topic_notes=len(topic_papers),
        venue_notes=len(venue_papers),
        author_notes=len(author_papers) if include_authors else 0,
        possible_overlaps=len(overlap_candidates),
        manifest=manifest,
        index=index_path,
        overlap_report=overlap_path,
    )
