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


GRAPH_IMPORT_MODE = "paper_universe_graph"
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
    return "source_tool: scholar-alert-reader" in head and f"obsidian_import: {GRAPH_IMPORT_MODE}" in head


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


def paper_frontmatter(record: dict[str, Any], topics: list[str], collections: list[str]) -> list[str]:
    return [
        "---",
        "type: paper",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {GRAPH_IMPORT_MODE}",
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
        f"graph_topics: {yaml_list(topics)}",
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
) -> str:
    lines = [
        "---",
        f"type: {node_type}",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {GRAPH_IMPORT_MODE}",
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


def normalize_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def title_similarity(a: str, b: str) -> float:
    a_tokens = set(normalize_title(a).split())
    b_tokens = set(normalize_title(b).split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def possible_zotero_scholar_overlaps(records: list[dict[str, Any]], threshold: float = 0.82, limit: int = 120) -> list[dict[str, Any]]:
    scholar = [record for record in records if "scholar_alert" in set(coerce_list(record.get("source_types"))) and "zotero" not in set(coerce_list(record.get("source_types")))]
    zotero = [record for record in records if "zotero" in set(coerce_list(record.get("source_types"))) and "scholar_alert" not in set(coerce_list(record.get("source_types")))]
    by_first_token: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in zotero:
        tokens = normalize_title(paper_title(record)).split()
        if tokens:
            by_first_token[tokens[0]].append(record)
    candidates: list[dict[str, Any]] = []
    for record in scholar:
        tokens = normalize_title(paper_title(record)).split()
        if not tokens:
            continue
        for other in by_first_token.get(tokens[0], []):
            score = title_similarity(paper_title(record), paper_title(other))
            if score < threshold:
                continue
            year_a = record_year(record)
            year_b = record_year(other)
            if year_a and year_b and abs(int(year_a) - int(year_b)) > 2:
                continue
            candidates.append(
                {
                    "score": round(score, 3),
                    "scholar": record,
                    "zotero": other,
                }
            )
    candidates.sort(key=lambda item: (-float(item["score"]), paper_title(item["scholar"]).lower()))
    return candidates[:limit]


def render_overlap_report(candidates: list[dict[str, Any]]) -> str:
    lines = [
        "---",
        "type: overlap_report",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {GRAPH_IMPORT_MODE}",
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
    lines.extend(["| Similarity | Scholar Alert paper | Zotero paper |", "|---:|---|---|"])
    for item in candidates:
        scholar = item["scholar"]
        zotero = item["zotero"]
        lines.append(
            f"| {item['score']:.3f} | {wikilink(paper_note_name(scholar), paper_title(scholar))} | {wikilink(paper_note_name(zotero), paper_title(zotero))} |"
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
) -> str:
    source_counts = Counter()
    for record in records:
        source_counts.update(str(item) for item in coerce_list(record.get("source_types")) if str(item).strip())
    lines = [
        "---",
        "type: literature_graph_index",
        "generated: true",
        "source_tool: scholar-alert-reader",
        f"obsidian_import: {GRAPH_IMPORT_MODE}",
        f"paper_count: {len(records)}",
        "---",
        "",
        "# Paper Universe Graph",
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


def export_obsidian_graph(
    records: list[dict[str, Any]],
    export_dir: Path,
    *,
    limit: int = 0,
    include_authors: bool = False,
    author_limit: int = 300,
    max_papers_per_node: int = 80,
    prune: bool = True,
) -> ObsidianGraphExportResult:
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
