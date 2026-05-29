"""RIS bibliography parser adapter."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import html
import re
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


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [text]


def first_value(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if isinstance(value, list):
            if value:
                return clean_bibliography_value(str(value[0]))
        elif value:
            return clean_bibliography_value(str(value))
    return ""


def split_keywords(value: Any) -> list[str]:
    keywords: list[str] = []
    for item in coerce_list(value):
        for part in re.split(r"\s*;\s*|\s*,\s*", item):
            cleaned = clean_bibliography_value(part)
            if cleaned and cleaned not in keywords:
                keywords.append(cleaned)
    return keywords


def bibliography_authors_source(authors: list[str], source: str, year: str) -> str:
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
    if source:
        parts.append(source)
    if year:
        parts.append(year)
    return " - ".join(parts)


def year_from_fields(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = first_value(fields, [name])
        match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
        if match:
            return match.group(0)
    return ""


def doi_url(doi: str) -> str:
    doi = doi.strip()
    if not doi:
        return ""
    if doi.lower().startswith(("http://", "https://")):
        return doi
    return f"https://doi.org/{doi}"


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


def parse_ris_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    last_tag = ""
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        tag_match = re.match(r"^([A-Z0-9]{2})\s{2}-\s?(.*)$", raw_line)
        if tag_match:
            tag = tag_match.group(1)
            value = clean_bibliography_value(tag_match.group(2))
            if tag == "TY":
                current = {"TY": value}
            elif tag == "ER":
                if current:
                    entries.append(current)
                current = {}
            elif current:
                existing = current.get(tag)
                if existing is None:
                    current[tag] = value
                elif isinstance(existing, list):
                    existing.append(value)
                else:
                    current[tag] = [existing, value]
            last_tag = tag
        elif current and last_tag:
            continuation = clean_bibliography_value(raw_line)
            existing = current.get(last_tag)
            if isinstance(existing, list) and existing:
                existing[-1] = " ".join([existing[-1], continuation]).strip()
            elif isinstance(existing, str):
                current[last_tag] = " ".join([existing, continuation]).strip()
    if current:
        entries.append(current)
    return entries


def paper_from_ris_entry(
    fields: dict[str, Any],
    source_path: Path,
    paper_factory: Callable[..., Any] | None = None,
) -> Any | None:
    if paper_factory is None:
        from ..core import Paper  # keep core dependency lazy to avoid import cycle

        paper_factory = Paper

    title = first_value(fields, ["TI", "T1", "CT"])
    if not title:
        return None
    authors = coerce_list(fields.get("AU") or fields.get("A1") or fields.get("A2"))
    source = first_value(fields, ["JO", "JF", "JA", "T2", "PB"])
    year = year_from_fields(fields, ["PY", "Y1", "DA"])
    doi = first_value(fields, ["DO"])
    url = first_value(fields, ["UR", "L1", "LK"]) or doi_url(doi)
    keywords = split_keywords(fields.get("KW"))
    abstract = first_value(fields, ["AB", "N2"])
    snippet = abstract or ("Keywords: " + ", ".join(keywords) if keywords else "Imported from RIS.")
    seen_date = file_seen_date(source_path)
    metadata = {
        "ris": {
            "type": first_value(fields, ["TY"]),
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
        alerts=[source_path.name, "RIS import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_ris_source(
    ris_path: Path,
    paper_factory: Callable[..., Any] | None = None,
) -> tuple[list[Any], dict[str, int]]:
    if paper_factory is None:
        from ..core import Paper  # keep core dependency lazy to avoid import cycle

        paper_factory = Paper

    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    for path in bibliography_paths(ris_path, ".ris"):
        counts["bibliography_files"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = parse_ris_entries(text)
        counts["bibliography_entries"] += len(entries)
        for entry in entries:
            paper = paper_from_ris_entry(entry, path, paper_factory=paper_factory)
            if paper is None:
                counts["bibliography_skipped_no_title"] += 1
                continue
            _merge_bibliography_paper(papers_by_key, paper)
    counts["bibliography_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)
