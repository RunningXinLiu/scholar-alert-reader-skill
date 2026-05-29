"""BibTeX bibliography parser adapter."""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import base


def clean_bibliography_value(value: str) -> str:
    value = strip_wrapping_pairs(value)
    replacements = {
        "\\&": "&",
        "\\%": "%",
        "\\_": "_",
        "\\textendash": "-",
        "\\textemdash": "-",
        "---": "-",
        "--": "-",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})", r"\1", value)
    value = value.replace("{", "").replace("}", "")
    return " ".join(html.unescape(value).split())


def strip_wrapping_pairs(value: str) -> str:
    value = value.strip()
    changed = True
    while changed and len(value) >= 2:
        changed = False
        if (value[0], value[-1]) in {("{", "}"), ("\"", "\"")}:
            value = value[1:-1].strip()
            changed = True
    return value


def read_balanced_value(text: str, start: int, opener: str, closer: str) -> tuple[str, int]:
    value_chars: list[str] = []
    pos = start
    if pos >= len(text) or text[pos] != opener:
        return "", pos
    pos += 1
    depth = 1
    while pos < len(text):
        char = text[pos]
        previous = text[pos - 1] if pos > 0 else ""
        if char == opener and previous != "\\":
            depth += 1
            value_chars.append(char)
        elif char == closer and previous != "\\":
            depth -= 1
            if depth == 0:
                return "".join(value_chars), pos + 1
            value_chars.append(char)
        else:
            value_chars.append(char)
        pos += 1
    return "".join(value_chars), pos


def split_top_level_comma(text: str) -> tuple[str, str]:
    brace_depth = 0
    quote_open = False
    for pos, char in enumerate(text):
        previous = text[pos - 1] if pos > 0 else ""
        if char == '"' and previous != "\\":
            quote_open = not quote_open
        elif not quote_open:
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == "," and brace_depth == 0:
                return text[:pos], text[pos + 1 :]
    return text, ""


def read_bibtex_field_value(text: str, start: int) -> tuple[str, int]:
    pos = start
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text):
        return "", pos
    if text[pos] == "{":
        return read_balanced_value(text, pos, "{", "}")
    if text[pos] == '"':
        pos += 1
        value_chars: list[str] = []
        while pos < len(text):
            char = text[pos]
            previous = text[pos - 1] if pos > 0 else ""
            if char == '"' and previous != "\\":
                return "".join(value_chars), pos + 1
            value_chars.append(char)
            pos += 1
        return "".join(value_chars), pos

    start_value = pos
    while pos < len(text) and text[pos] != ",":
        pos += 1
    return text[start_value:pos], pos


def parse_bibtex_fields(body: str) -> dict[str, str]:
    key_part, fields_part = split_top_level_comma(body)
    fields: dict[str, str] = {"_key": clean_bibliography_value(key_part)}
    pos = 0
    while pos < len(fields_part):
        while pos < len(fields_part) and fields_part[pos] in ", \n\r\t":
            pos += 1
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", fields_part[pos:])
        if not match:
            break
        field_name = match.group(1).lower()
        pos += match.end()
        raw_value, pos = read_bibtex_field_value(fields_part, pos)
        fields[field_name] = clean_bibliography_value(raw_value)
        while pos < len(fields_part) and fields_part[pos].isspace():
            pos += 1
        if pos < len(fields_part) and fields_part[pos] == ",":
            pos += 1
    return fields


def parse_bibtex_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    pos = 0
    while True:
        at = text.find("@", pos)
        if at == -1:
            break
        match = re.match(r"@([A-Za-z]+)\s*([\{\(])", text[at:])
        if not match:
            pos = at + 1
            continue
        entry_type = match.group(1).lower()
        opener = match.group(2)
        closer = "}" if opener == "{" else ")"
        body_start = at + match.end()
        body, next_pos = read_balanced_value(text, body_start - 1, opener, closer)
        if entry_type not in {"comment", "preamble", "string"}:
            fields = parse_bibtex_fields(body)
            fields["_type"] = entry_type
            entries.append(fields)
        pos = max(next_pos, at + 1)
    return entries


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [text]


def split_authors(value: str) -> list[str]:
    return [
        clean_bibliography_value(part)
        for part in re.split(r"\s+\band\b\s+|;\s*", value)
        if clean_bibliography_value(part)
    ]


def split_keywords(value: Any) -> list[str]:
    keywords: list[str] = []
    for item in coerce_list(value):
        for part in re.split(r"\s*;\s*|\s*,\s*", item):
            cleaned = clean_bibliography_value(part)
            if cleaned and cleaned not in keywords:
                keywords.append(cleaned)
    return keywords


def first_value(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if isinstance(value, list):
            if value:
                return clean_bibliography_value(str(value[0]))
        elif value:
            return clean_bibliography_value(str(value))
    return ""


def year_from_fields(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = first_value(fields, [name])
        match = re.search(r"\\b(18|19|20|21)\\d{2}\\b", value)
        if match:
            return match.group(0)
    return ""


def bibliography_authors_source(authors: list[str], source: str, year: str) -> str:
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
    if source:
        parts.append(source)
    if year:
        parts.append(year)
    return " - ".join(parts)


def doi_url(doi: str) -> str:
    doi = doi.strip()
    if not doi:
        return ""
    if doi.lower().startswith(("http://", "https://")):
        return doi
    return f"https://doi.org/{doi}"


def normalize_doi(doi: str) -> str:
    doi = clean_bibliography_value(doi)
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "")
    return doi.strip().lower()


def unquote_file_url(value: str) -> str:
    from urllib.parse import unquote, urlparse

    value = value.strip()
    if value.lower().startswith("file://"):
        parsed = urlparse(value)
        return unquote(parsed.path)
    return value


def extract_pdf_paths(value: str) -> list[str]:
    paths: list[str] = []
    if not value:
        return paths
    for item in re.split(r"\s*;\s*", value):
        remaining = item
        for match in re.finditer(r"file://[^\s;]+?\.pdf", item, flags=re.IGNORECASE):
            path = unquote_file_url(match.group(0))
            if path and path not in paths:
                paths.append(path)
            remaining = remaining.replace(match.group(0), " ")
        for pattern in [
            r"(?<![A-Za-z0-9])(?:~|/)[^;]+?\\.pdf",
            r"(?<![A-Za-z])[A-Za-z]:[\\/][^;]+?\.pdf",
        ]:
            for match in re.finditer(pattern, remaining, flags=re.IGNORECASE):
                path = unquote_file_url(match.group(0))
                if path and path not in paths:
                    paths.append(path)
    return paths


def first_nonempty_field(fields: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if value:
            return value
    return ""


def zotero_item_key_from_fields(fields: dict[str, str]) -> str:
    direct = first_nonempty_field(fields, ["zotero-key", "zoterokey", "item-key", "itemkey"])
    if direct:
        return direct
    for name in ["uri", "zotero-select", "zotero-uri"]:
        value = fields.get(name, "")
        match = re.search(r"/items/([A-Za-z0-9]+)", value)
        if match:
            return match.group(1)
    return ""


def zotero_metadata_from_bibtex_fields(fields: dict[str, str], source_path: Path) -> dict[str, Any]:
    pdf_paths: list[str] = []
    for name, value in fields.items():
        if name == "file" or name.startswith("bdsk-file") or "attachment" in name or name in {"pdf", "local-url"}:
            for path in extract_pdf_paths(value):
                if path not in pdf_paths:
                    pdf_paths.append(path)
    return {
        "citation_key": fields.get("_key", ""),
        "item_key": zotero_item_key_from_fields(fields),
        "doi": first_value(fields, ["doi"]),
        "title": first_value(fields, ["title"]),
        "pdf_paths": pdf_paths,
        "uri": first_nonempty_field(fields, ["uri", "zotero-select", "zotero-uri"]),
        "source_files": [str(source_path)],
        "synced_at": datetime.now().isoformat(timespec="seconds"),
    }


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


def file_seen_date(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    except OSError:
        return datetime.now().date().isoformat()


def bibliography_paths(path: Path, suffix: str) -> list[Path]:
    path = path.expanduser()
    if not path.exists():
        raise SystemExit(f"Cannot find bibliography source: {path}")
    if path.is_dir():
        paths = sorted(path.glob(f"*{suffix}"))
        if not paths:
            raise SystemExit(f"No {suffix} files found in directory: {path}")
        return paths
    return [path]


def paper_from_bibtex_entry(
    fields: dict[str, str],
    source_path: Path,
    paper_factory: Callable[..., Any] | None = None,
) -> Any | None:
    if paper_factory is None:
        from ..core import Paper  # keep core dependency lazy to avoid import cycle.

        paper_factory = Paper

    title = first_value(fields, ["title"])
    if not title:
        return None
    authors = split_authors(first_value(fields, ["author", "editor"]))
    source = first_value(fields, ["journal", "journaltitle", "booktitle", "publisher", "school", "institution"])
    year = year_from_fields(fields, ["year", "date"])
    doi = first_value(fields, ["doi"])
    url = first_value(fields, ["url", "link"]) or doi_url(doi)
    keywords = split_keywords(fields.get("keywords") or fields.get("keyword"))
    abstract = first_value(fields, ["abstract", "annote", "note"])
    snippet = abstract or ("Keywords: " + ", ".join(keywords) if keywords else "Imported from BibTeX.")
    seen_date = file_seen_date(source_path)
    metadata = {
        "bibtex": {
            "entry_type": fields.get("_type", ""),
            "key": fields.get("_key", ""),
            "doi": doi,
            "year": year,
            "source": source,
            "authors": authors,
            "keywords": keywords,
        }
    }
    return paper_factory(
        id=base.stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source, year),
        snippet=snippet,
        url=url,
        scholar_url="",
        first_seen=seen_date,
        last_seen=seen_date,
        alerts=[source_path.name, "BibTeX import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_bibtex_source(
    bibtex_path: Path,
    paper_factory: Callable[..., Any] | None = None,
) -> tuple[list[Any], dict[str, int]]:
    if paper_factory is None:
        from ..core import Paper  # keep core dependency lazy to avoid import cycle.

        paper_factory = Paper

    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    for path in bibliography_paths(bibtex_path, ".bib"):
        counts["bibliography_files"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = parse_bibtex_entries(text)
        counts["bibliography_entries"] += len(entries)
        for entry in entries:
            paper = paper_from_bibtex_entry(entry, path, paper_factory=paper_factory)
            if paper is None:
                counts["bibliography_skipped_no_title"] += 1
                continue
            _merge_bibliography_paper(papers_by_key, paper)
    counts["bibliography_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)
