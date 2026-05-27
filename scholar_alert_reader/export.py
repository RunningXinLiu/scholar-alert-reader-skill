"""Export helpers for retained Scholar Alert Reader papers."""

from __future__ import annotations

import json
import re
from typing import Any


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def metadata(record: dict[str, Any], provider: str) -> dict[str, Any]:
    data = record.get("metadata") or {}
    value = data.get(provider)
    return value if isinstance(value, dict) else {}


def best_doi(record: dict[str, Any]) -> str:
    doi = metadata(record, "openalex").get("doi") or metadata(record, "crossref").get("doi") or ""
    return str(doi).replace("https://doi.org/", "").strip()


def best_year(record: dict[str, Any]) -> str:
    year = metadata(record, "openalex").get("publication_year")
    if year:
        return str(year)
    source = str(record.get("authors_source", ""))
    match = re.search(r"\b(19|20)\d{2}\b", source)
    return match.group(0) if match else ""


def best_journal(record: dict[str, Any]) -> str:
    return clean_text(
        metadata(record, "openalex").get("source")
        or metadata(record, "crossref").get("container_title")
        or ""
    )


def best_authors(record: dict[str, Any]) -> list[str]:
    authors = metadata(record, "openalex").get("authors")
    if isinstance(authors, list) and authors:
        return [clean_text(author) for author in authors if clean_text(author)]
    source = str(record.get("authors_source", ""))
    prefix = source.split(" - ", 1)[0]
    if not prefix:
        return []
    return [clean_text(author) for author in re.split(r",| and ", prefix) if clean_text(author)]


def cite_key(record: dict[str, Any], existing: set[str]) -> str:
    authors = best_authors(record)
    first_author = "paper"
    if authors:
        first_author = re.sub(r"[^a-zA-Z0-9]+", "", authors[0].split()[-1]).lower() or "paper"
    title_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9]{3,}", str(record.get("title", "")).lower())
    title_part = "".join(title_terms[:2]) or "alert"
    year = best_year(record) or "nd"
    base = f"{first_author}{year}{title_part}"
    key = base
    suffix = 2
    while key in existing:
        key = f"{base}{suffix}"
        suffix += 1
    existing.add(key)
    return key


def bibtex_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def render_bibtex(records: list[dict[str, Any]]) -> str:
    keys: set[str] = set()
    entries: list[str] = []
    for record in records:
        key = cite_key(record, keys)
        fields = {
            "title": clean_text(record.get("title")),
            "author": " and ".join(best_authors(record)),
            "year": best_year(record),
            "journal": best_journal(record),
            "doi": best_doi(record),
            "url": clean_text(record.get("url")),
            "keywords": ", ".join(
                clean_text(value)
                for value in list(record.get("matched_terms", [])) + list(record.get("tags", []))
                if clean_text(value)
            ),
            "abstract": clean_text(record.get("snippet")),
        }
        lines = [f"@article{{{key},"]
        for name, value in fields.items():
            if value:
                lines.append(f"  {name} = {{{bibtex_escape(value)}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries).rstrip() + "\n"


def render_ris(records: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for record in records:
        lines = ["TY  - JOUR", f"TI  - {clean_text(record.get('title'))}"]
        for author in best_authors(record):
            lines.append(f"AU  - {author}")
        year = best_year(record)
        if year:
            lines.append(f"PY  - {year}")
        journal = best_journal(record)
        if journal:
            lines.append(f"JO  - {journal}")
        doi = best_doi(record)
        if doi:
            lines.append(f"DO  - {doi}")
        url = clean_text(record.get("url"))
        if url:
            lines.append(f"UR  - {url}")
        snippet = clean_text(record.get("snippet"))
        if snippet:
            lines.append(f"AB  - {snippet}")
        keywords = [clean_text(value) for value in list(record.get("matched_terms", [])) + list(record.get("tags", [])) if clean_text(value)]
        for keyword in keywords[:20]:
            lines.append(f"KW  - {keyword}")
        lines.append("ER  -")
        entries.append("\n".join(lines))
    return "\n\n".join(entries).rstrip() + "\n"


def render_markdown(records: list[dict[str, Any]]) -> str:
    lines = ["# Scholar Alert Export", ""]
    for record in records:
        title = clean_text(record.get("title")) or "Untitled"
        url = clean_text(record.get("url"))
        score = record.get("score", 0)
        tier = clean_text(record.get("tier"))
        year = best_year(record)
        doi = best_doi(record)
        journal = best_journal(record)
        authors = ", ".join(best_authors(record)[:8])
        heading = f"## [{title}]({url})" if url else f"## {title}"
        lines.extend(
            [
                heading,
                "",
                f"- Tier: {tier}; score: {score}",
                f"- Authors: {authors}",
                f"- Year: {year}",
                f"- Source: {journal or clean_text(record.get('authors_source'))}",
                f"- DOI: {doi}",
                f"- Matched: {', '.join(record.get('matched_terms', []))}",
                "",
                clean_text(record.get("snippet")),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records) + "\n"


def export_records(records: list[dict[str, Any]], fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "bibtex":
        return render_bibtex(records)
    if fmt == "ris":
        return render_ris(records)
    if fmt == "markdown":
        return render_markdown(records)
    if fmt == "jsonl":
        return render_jsonl(records)
    raise ValueError(f"Unsupported export format: {fmt}")
