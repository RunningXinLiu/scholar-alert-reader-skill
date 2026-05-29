"""Webpage metadata parser adapter."""

from __future__ import annotations

import html
from collections import Counter
import re
import json
from pathlib import Path
from typing import Any, Callable

from . import base
from . import rss


def is_url(value: str) -> bool:
    return rss.is_url(value)


def split_csv(value: str | None) -> list[str]:
    return rss.split_csv(value)


def feed_date(value: str) -> str:
    return rss.feed_date(value)


def read_web_text(source: str, timeout: int) -> str:
    return rss.read_feed_text(source, timeout)


def web_sources(source: str) -> list[str]:
    source = str(source).strip()
    if not source:
        raise SystemExit("Web source is empty.")
    path = Path(source).expanduser()
    if path.exists():
        if path.is_dir():
            files = sorted(
                item
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in {".html", ".htm"}
            )
            if not files:
                raise SystemExit(f"No .html/.htm files found in directory: {path}")
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
                raise SystemExit(f"No webpage URLs or paths found in: {path}")
            return lines
        return [str(path)]
    return split_csv(source) or [source]


def _clean_html(fragment: str) -> str:
    fragment = fragment.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    fragment = html.unescape(fragment)
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def parse_html_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(
        r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
        tag,
    ):
        key = match.group(1).lower()
        value = match.group(2).strip().strip("\"'")
        attrs[key] = html.unescape(value)
    return attrs


def web_meta_fields(page_html: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for tag in re.findall(r"<meta\b[^>]*>", page_html, flags=re.IGNORECASE | re.DOTALL):
        attrs = parse_html_attrs(tag)
        key = (attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or "").strip().lower()
        content = attrs.get("content", "").strip()
        if key and content:
            fields.setdefault(key, []).append(content)
    title_match = re.search(
        r"<title\b[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL
    )
    if title_match:
        title = _clean_html(title_match.group(1))
        if title:
            fields.setdefault("html:title", []).append(title)
    return fields


def first_web_value(fields: dict[str, list[str]], names: list[str]) -> str:
    for name in names:
        values = fields.get(name.lower(), [])
        for value in values:
            cleaned = _clean_html(str(value))
            if cleaned:
                return cleaned
    return ""


def web_values(fields: dict[str, list[str]], names: list[str]) -> list[str]:
    values: list[str] = []
    for name in names:
        for value in fields.get(name.lower(), []):
            cleaned = _clean_html(str(value))
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values


def jsonld_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                items.extend(jsonld_items(item))
        item_type = value.get("@type", "")
        types = item_type if isinstance(item_type, list) else [item_type]
        normalized = {str(item).lower() for item in types}
        if normalized & {"scholarlyarticle", "article", "report", "techarticle"}:
            items.append(value)
    elif isinstance(value, list):
        for item in value:
            items.extend(jsonld_items(item))
    return items


def jsonld_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    authors: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _clean_html(str(item.get("name", "")))
        else:
            name = _clean_html(str(item))
        if name and name not in authors:
            authors.append(name)
    return authors


def jsonld_source(value: dict[str, Any]) -> str:
    for key in ["isPartOf", "publisher", "sourceOrganization"]:
        item = value.get(key)
        if isinstance(item, dict):
            name = _clean_html(str(item.get("name", "")))
            if name:
                return name
        elif isinstance(item, str) and item.strip():
            return _clean_html(item)
    return ""


def jsonld_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, list):
        for item in value:
            values.extend(jsonld_text_values(item))
    elif isinstance(value, dict):
        for key in ["value", "name", "@id", "url"]:
            item = value.get(key)
            if item:
                values.extend(jsonld_text_values(item))
                break
    elif value:
        text = _clean_html(str(value))
        if text:
            values.append(text)
    return values


def jsonld_to_web_fields(item: dict[str, Any]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    mapping = {
        "citation_title": ["headline", "name"],
        "citation_abstract": ["abstract", "description"],
        "citation_publication_date": ["datePublished", "dateCreated", "dateModified"],
        "citation_public_url": ["url", "mainEntityOfPage"],
        "citation_doi": ["doi", "identifier"],
    }
    for target, keys in mapping.items():
        for key in keys:
            values = jsonld_text_values(item.get(key))
            if values:
                fields.setdefault(target, []).extend(values)
                break
    for author in jsonld_authors(item.get("author") or item.get("creator")):
        fields.setdefault("citation_author", []).append(author)
    source = jsonld_source(item)
    if source:
        fields.setdefault("citation_journal_title", []).append(source)
    for key in ["encoding", "associatedMedia"]:
        value = item.get(key)
        values = value if isinstance(value, list) else [value] if value else []
        for entry in values:
            if not isinstance(entry, dict):
                continue
            content_url = _clean_html(str(entry.get("contentUrl") or entry.get("url") or ""))
            encoding_format = str(entry.get("encodingFormat") or entry.get("fileFormat") or "").lower()
            if content_url and ("pdf" in encoding_format or content_url.lower().split("?")[0].endswith(".pdf")):
                fields.setdefault("citation_pdf_url", []).append(content_url)
    return fields


def bibliography_authors_source(authors: list[str], source: str, year: str) -> str:
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
    if source:
        parts.append(source)
    if year:
        parts.append(year)
    return " - ".join(parts)


def paper_from_web_fields(fields: dict[str, list[str]], source_name: str, paper_factory: Callable[..., Any] | None = None) -> Any | None:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper

    title = first_web_value(fields, ["citation_title", "dc.title", "dcterms.title", "og:title", "twitter:title", "html:title"])
    if not title:
        return None
    authors = web_values(fields, ["citation_author", "dc.creator", "dcterms.creator", "author"])
    source = first_web_value(fields, ["citation_journal_title", "citation_conference_title", "dc.source", "og:site_name"])
    date_value = first_web_value(fields, ["citation_publication_date", "citation_date", "dc.date", "dcterms.date", "article:published_time"])
    date = feed_date(date_value)
    doi = clean_doi(first_web_value(fields, ["citation_doi", "dc.identifier", "doi"]))
    url = first_web_value(fields, ["citation_public_url", "citation_fulltext_html_url", "og:url", "twitter:url"]) or doi_url(doi) or source_name
    pdf_url = first_web_value(fields, ["citation_pdf_url", "citation_fulltext_pdf_url", "dc.format.pdf"])
    snippet = first_web_value(fields, ["citation_abstract", "dc.description", "dcterms.description", "description", "og:description", "twitter:description"])
    keywords = web_values(fields, ["citation_keywords", "keywords", "dc.subject", "article:tag"])
    if not snippet and keywords:
        snippet = "Keywords: " + ", ".join(keywords)

    metadata = {
        "web": {
            "source": source_name,
            "doi": doi,
            "published": date_value,
            "authors": authors,
            "keywords": keywords,
            "pdf_url": pdf_url,
        }
    }
    return paper_factory(
        id=base.stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source or source_name, date[:4]),
        snippet=snippet or "Imported from webpage metadata.",
        url=url,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source or source_name, "Web metadata import"],
        occurrences=1,
        metadata=metadata,
    )


def clean_doi(doi: str) -> str:
    return doi.replace("https://doi.org/", "").replace("http://doi.org/", "").lower().strip()


def doi_url(doi: str) -> str:
    doi = doi.strip()
    if not doi:
        return ""
    if doi.startswith(("http://", "https://")):
        return doi
    return f"https://doi.org/{doi}"


def parse_web_page(page_html: str, source_name: str, paper_factory: Callable[..., Any] | None = None) -> tuple[list[Any], dict[str, int]]:
    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    meta_fields = web_meta_fields(page_html)
    jsonld_count = 0
    for raw_script in re.findall(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_json = html.unescape(raw_script).strip()
        if not raw_json:
            continue
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            counts["web_jsonld_parse_errors"] += 1
            continue
        for item in jsonld_items(parsed):
            jsonld_count += 1
            paper = paper_from_web_fields({**meta_fields, **jsonld_to_web_fields(item)}, source_name, paper_factory=paper_factory)
            if paper is None:
                counts["web_skipped_no_title"] += 1
                continue
            _merge_paper(papers_by_key, paper)
    if not papers_by_key:
        paper = paper_from_web_fields(meta_fields, source_name, paper_factory=paper_factory)
        if paper:
            _merge_paper(papers_by_key, paper)
        else:
            counts["web_skipped_no_title"] += 1
    counts["web_jsonld_items"] = jsonld_count
    counts["web_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def _merge_paper(papers_by_key: dict[str, Any], paper: Any) -> None:
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


def parse_web_source(source: str, timeout: int = 20, limit: int = 0, paper_factory: Callable[..., Any] | None = None) -> tuple[list[Any], dict[str, int]]:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper
    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    for web_source in web_sources(source):
        counts["web_sources"] += 1
        text = read_web_text(web_source, timeout)
        papers, page_counts = parse_web_page(text, web_source, paper_factory=paper_factory)
        counts.update(page_counts)
        for paper in papers:
            _merge_paper(papers_by_key, paper)
    papers = list(papers_by_key.values())
    papers.sort(key=lambda paper: (paper.last_seen, paper.title.lower()), reverse=True)
    if limit > 0:
        papers = papers[:limit]
    counts["web_unique_papers"] = len(papers_by_key)
    counts["web_returned_papers"] = len(papers)
    return papers, dict(counts)
