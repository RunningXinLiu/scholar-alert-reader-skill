"""RSS/Atom parser adapter."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .. import __version__
from . import base


def is_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_message_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def feed_date(value: str) -> str:
    value = value.strip()
    if not value:
        return datetime.now().date().isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        pass
    parsed_email_date = _parse_message_date(value)
    if parsed_email_date:
        return parsed_email_date.date().isoformat()
    match = re.search(r"\b(18|19|20|21)\d{2}-\d{2}-\d{2}\b", value)
    if match:
        return match.group(0)
    return datetime.now().date().isoformat()


def read_feed_text(source: str, timeout: int) -> str:
    source = str(source).strip()
    if is_url(source):
        request = Request(source, headers={"User-Agent": f"ScholarAlertReader/{__version__}"})
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    return Path(source).expanduser().read_text(encoding="utf-8", errors="replace")


def rss_sources(source: str) -> list[str]:
    source = str(source).strip()
    if not source:
        raise SystemExit("RSS/Atom source is empty.")
    path = Path(source).expanduser()
    if path.exists():
        if path.is_dir():
            files = sorted(
                item
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in {".xml", ".rss", ".atom"}
            )
            if not files:
                raise SystemExit(f"No .xml/.rss/.atom feed files found in directory: {path}")
            return [str(item) for item in files]
        if path.suffix.lower() in {".txt", ".list"}:
            lines: list[str] = []
            for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.lstrip().startswith("#"):
                    continue
                line_path = Path(line).expanduser()
                if not is_url(line) and not line_path.is_absolute():
                    line = str(path.parent / line_path)
                lines.append(line)
            if not lines:
                raise SystemExit(f"No feed URLs or paths found in: {path}")
            return lines
        return [str(path)]
    return split_csv(source) or [source]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def child_text(element: ET.Element, name: str) -> str:
    for child in list(element):
        if local_name(child.tag) == name:
            return _clean_html("".join(child.itertext()))
    return ""


def children_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def _clean_html(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = fragment.replace("&nbsp;", " ")
    return " ".join(fragment.split())


def _merge_bibliography_paper(papers_by_key: dict[str, Any], paper: Any) -> None:
    key = base.normalize_title(paper.title)
    existing = papers_by_key.get(key)
    if existing is None:
        papers_by_key[key] = paper
        return
    existing.occurrences += paper.occurrences
    for alert in paper.alerts:
        if alert not in existing.alerts:
            existing.alerts.append(alert)
    dates = [date for date in [existing.first_seen, existing.last_seen, paper.first_seen, paper.last_seen] if date]
    if dates:
        existing.first_seen = min(dates)
        existing.last_seen = max(dates)
    if len(paper.snippet) > len(existing.snippet):
        existing.snippet = paper.snippet
    if not existing.url and paper.url:
        existing.url = paper.url
    if not existing.authors_source and paper.authors_source:
        existing.authors_source = paper.authors_source
    existing.metadata = {**existing.metadata, **paper.metadata}


def atom_link(entry: ET.Element) -> str:
    fallback = ""
    for link in children_named(entry, "link"):
        href = link.attrib.get("href", "").strip()
        rel = link.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
    return fallback or child_text(entry, "id")


def feed_authors(entry: ET.Element) -> list[str]:
    authors: list[str] = []
    for author in children_named(entry, "author"):
        name = child_text(author, "name") or _clean_html("".join(author.itertext()))
        if name and name not in authors:
            authors.append(name)
    creator = child_text(entry, "creator")
    if creator:
        for part in re.split(r"\s*;\s*|\s*,\s*", creator):
            if part and part not in authors:
                authors.append(part)
    return authors


def _bibliography_authors_source(authors: list[str], source: str, year: str) -> str:
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
    if source:
        parts.append(source)
    if year:
        parts.append(year)
    return " - ".join(parts)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [text] if isinstance(value, str) else [str(item).strip() for item in value if str(item).strip()]


def paper_from_atom_entry(
    entry: ET.Element,
    feed_title: str,
    source_name: str,
    paper_factory: Callable[..., Any] | None = None,
) -> Any | None:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper
    title = child_text(entry, "title")
    if not title:
        return None
    authors = feed_authors(entry)
    summary = child_text(entry, "summary") or child_text(entry, "content")
    published = child_text(entry, "published") or child_text(entry, "updated")
    date = feed_date(published)
    url = atom_link(entry)
    categories = [category.attrib.get("term", "").strip() for category in children_named(entry, "category") if category.attrib.get("term", "").strip()]
    arxiv_id = ""
    if "arxiv.org" in url:
        arxiv_id = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", url).replace(".pdf", "")
    source = feed_title or source_name
    metadata = {
        "arxiv" if arxiv_id else "feed": {
            "id": arxiv_id or child_text(entry, "id"),
            "published": published,
            "updated": child_text(entry, "updated"),
            "source": source,
            "categories": categories,
            "authors": authors,
        }
    }
    return paper_factory(
        id=base.stable_id(title),
        title=title,
        authors_source=_bibliography_authors_source(authors, source, date[:4]),
        snippet=summary or "Imported from Atom/RSS feed.",
        url=url,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source, "Atom/RSS import"],
        occurrences=1,
        metadata=metadata,
    )


def paper_from_rss_item(
    item: ET.Element,
    feed_title: str,
    source_name: str,
    paper_factory: Callable[..., Any] | None = None,
) -> Any | None:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper
    title = child_text(item, "title")
    if not title:
        return None
    link = child_text(item, "link") or child_text(item, "guid")
    summary = child_text(item, "description") or child_text(item, "summary") or child_text(item, "encoded")
    published = child_text(item, "pubDate") or child_text(item, "date") or child_text(item, "updated")
    date = feed_date(published)
    authors = _coerce_list(child_text(item, "author") or child_text(item, "creator"))
    categories = [_clean_html("".join(category.itertext())) for category in children_named(item, "category")]
    source = feed_title or source_name
    metadata = {
        "feed": {
            "id": child_text(item, "guid") or link,
            "published": published,
            "source": source,
            "categories": [category for category in categories if category],
            "authors": authors,
        }
    }
    return paper_factory(
        id=base.stable_id(title),
        title=title,
        authors_source=_bibliography_authors_source(authors, source, date[:4]),
        snippet=summary or "Imported from RSS feed.",
        url=link,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source, "RSS import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_feed_xml(text: str, source_name: str, paper_factory: Callable[..., Any] | None = None) -> tuple[list[Any], dict[str, int]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SystemExit(f"Cannot parse RSS/Atom feed {source_name}: {exc}") from exc
    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    root_name = local_name(root.tag).lower()
    if root_name == "feed":
        feed_title = child_text(root, "title") or source_name
        entries = children_named(root, "entry")
        counts["feed_entries"] = len(entries)
        for entry in entries:
            paper = paper_from_atom_entry(entry, feed_title, source_name, paper_factory=paper_factory)
            if paper is None:
                counts["feed_skipped_no_title"] += 1
                continue
            _merge_bibliography_paper(papers_by_key, paper)
    else:
        channel = next((child for child in children_named(root, "channel")), root)
        feed_title = child_text(channel, "title") or source_name
        items = children_named(channel, "item") or [item for item in root.iter() if local_name(item.tag) == "item"]
        counts["feed_entries"] = len(items)
        for item in items:
            paper = paper_from_rss_item(item, feed_title, source_name, paper_factory=paper_factory)
            if paper is None:
                counts["feed_skipped_no_title"] += 1
                continue
            _merge_bibliography_paper(papers_by_key, paper)
    counts["feed_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def parse_rss_source(source: str, timeout: int = 20, limit: int = 0, paper_factory: Callable[..., Any] | None = None) -> tuple[list[Any], dict[str, int]]:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper
    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    for feed_source in rss_sources(source):
        counts["feed_sources"] += 1
        text = read_feed_text(feed_source, timeout)
        papers, feed_counts = parse_feed_xml(text, feed_source, paper_factory=paper_factory)
        counts.update(feed_counts)
        for paper in papers:
            _merge_bibliography_paper(papers_by_key, paper)
    papers = list(papers_by_key.values())
    papers.sort(key=lambda paper: (paper.last_seen, paper.title.lower()), reverse=True)
    if limit > 0:
        papers = papers[:limit]
    counts["feed_unique_papers"] = len(papers_by_key)
    counts["feed_returned_papers"] = len(papers)
    return papers, dict(counts)
