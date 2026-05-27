"""Local full-text extraction and reading-brief helpers."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .copilot import profile_terms, text


@dataclass
class ExtractedText:
    text: str
    method: str
    source_path: Path


def clean_full_text(value: str, max_chars: int = 120_000) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:max_chars]


def extract_with_pdftotext(path: Path, timeout: int) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        return ""
    result = subprocess.run(
        [executable, "-layout", str(path), "-"],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def extract_with_python_pdf(path: Path) -> str:
    if importlib.util.find_spec("pypdf") is not None:
        from pypdf import PdfReader
    elif importlib.util.find_spec("PyPDF2") is not None:
        from PyPDF2 import PdfReader
    else:
        return ""
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages)


def extract_local_text(path: Path, max_chars: int = 120_000, timeout: int = 30) -> ExtractedText:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Full-text source not found: {path}")
    if path.suffix.lower() in {".txt", ".md"}:
        return ExtractedText(clean_full_text(path.read_text(encoding="utf-8", errors="replace"), max_chars), "text-file", path)
    if path.suffix.lower() != ".pdf":
        raise RuntimeError(f"Unsupported full-text source type: {path.suffix}. Use a PDF, .txt, or .md file.")

    extracted = extract_with_pdftotext(path, timeout)
    if extracted.strip():
        return ExtractedText(clean_full_text(extracted, max_chars), "pdftotext", path)
    extracted = extract_with_python_pdf(path)
    if extracted.strip():
        return ExtractedText(clean_full_text(extracted, max_chars), "python-pdf", path)
    raise RuntimeError(
        "Could not extract PDF text. Install `pdftotext` (poppler) or Python package `pypdf`, "
        "or pass a text export with --pdf-path."
    )


def zotero_pdf_paths(record: dict[str, Any]) -> list[str]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    zotero = metadata.get("zotero") if isinstance(metadata.get("zotero"), dict) else {}
    values = zotero.get("pdf_paths", []) if isinstance(zotero, dict) else []
    if isinstance(values, list):
        return [str(value) for value in values if str(value).strip()]
    if values:
        return [str(values)]
    return []


def first_full_text_path(record: dict[str, Any], explicit_path: Path | None = None) -> Path:
    if explicit_path:
        return explicit_path.expanduser()
    for value in zotero_pdf_paths(record):
        path = Path(value).expanduser()
        if path.exists():
            return path
    paths = zotero_pdf_paths(record)
    if paths:
        return Path(paths[0]).expanduser()
    raise FileNotFoundError("No local PDF/text path found. Run zotero-sync first or pass --pdf-path.")


def sentence_candidates(full_text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", full_text)
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [part.strip() for part in parts if 80 <= len(part.strip()) <= 420]


def profile_hits_in_text(full_text: str, profile: dict[str, Any]) -> list[str]:
    lower = full_text.lower()
    hits: list[str] = []
    for term in profile_terms(profile):
        if term.lower() in lower and term not in hits:
            hits.append(term)
    return hits


def representative_sentences(full_text: str, profile: dict[str, Any], limit: int = 8) -> list[str]:
    hits = profile_hits_in_text(full_text, profile)
    candidates = sentence_candidates(full_text)
    scored: list[tuple[int, str]] = []
    for sentence in candidates:
        lower = sentence.lower()
        score = sum(3 for term in hits if term.lower() in lower)
        score += len(re.findall(r"\b(method|data|result|model|inversion|tomography|earthquake|seismic|uncertainty)\b", lower))
        if score > 0:
            scored.append((score, sentence))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    selected: list[str] = []
    for _, sentence in scored:
        if sentence not in selected:
            selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected


def top_full_text_terms(full_text: str, limit: int = 20) -> list[tuple[str, int]]:
    tokens = re.findall(r"[a-z][a-z0-9-]{3,}", full_text.lower())
    stop = {
        "that",
        "this",
        "with",
        "from",
        "were",
        "have",
        "their",
        "using",
        "between",
        "figure",
        "table",
        "data",
        "paper",
        "study",
        "results",
    }
    return Counter(token.strip("-") for token in tokens if token.strip("-") not in stop).most_common(limit)


def find_section_excerpt(full_text: str, names: list[str], max_chars: int = 900) -> str:
    pattern = r"(?im)^\s*(?:" + "|".join(re.escape(name) for name in names) + r")\s*$"
    match = re.search(pattern, full_text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"(?m)^\s*[A-Z][A-Za-z \-/]{2,60}\s*$", full_text[start + 1 :])
    end = start + 1 + next_heading.start() if next_heading else min(len(full_text), start + max_chars)
    return clean_full_text(full_text[start:end], max_chars=max_chars)


def render_full_text_brief(
    record: dict[str, Any],
    extracted: ExtractedText,
    profile: dict[str, Any],
    text_output: Path,
) -> str:
    full_text = extracted.text
    hits = profile_hits_in_text(full_text, profile)
    terms = top_full_text_terms(full_text, 16)
    sentences = representative_sentences(full_text, profile, 8)
    abstract = find_section_excerpt(full_text, ["Abstract", "Summary"], max_chars=900)
    methods = find_section_excerpt(full_text, ["Methods", "Method", "Data and Methods", "Methodology"], max_chars=900)
    conclusions = find_section_excerpt(full_text, ["Conclusions", "Conclusion", "Discussion and Conclusions"], max_chars=900)

    lines = [
        f"# Full-Text Brief: {text(record.get('title', 'Untitled'))}",
        "",
        f"- Paper ID: `{record.get('id', '')}`",
        f"- Source file: `{extracted.source_path}`",
        f"- Extraction method: {extracted.method}",
        f"- Extracted characters: {len(full_text)}",
        f"- Text cache: `{text_output}`",
        "",
        "## Scope",
        "",
        "This is a local full-text extraction scaffold. It does not replace expert reading; use it to decide what to ask Codex or what to inspect manually in the PDF.",
        "",
        "## Profile Overlap",
        "",
    ]
    lines.append("- " + ", ".join(hits[:20]) if hits else "- No configured profile terms were found verbatim in the extracted text.")
    lines.extend(["", "## Frequent Terms", ""])
    lines.append("- " + "; ".join(f"{term} ({count})" for term, count in terms) if terms else "- No stable terms extracted.")
    if abstract:
        lines.extend(["", "## Abstract / Summary Excerpt", "", abstract])
    if methods:
        lines.extend(["", "## Methods Excerpt", "", methods])
    if conclusions:
        lines.extend(["", "## Conclusion Excerpt", "", conclusions])
    lines.extend(["", "## Sentences To Inspect", ""])
    if sentences:
        lines.extend(f"- {sentence}" for sentence in sentences)
    else:
        lines.append("- No profile-weighted sentences found. Inspect the text cache manually.")
    lines.extend(
        [
            "",
            "## Follow-Up Prompts",
            "",
            "- Compare this full-text brief against the alert-only deep-read report.",
            "- Identify the paper's actual method, dataset, region, assumptions, and limitations from the text cache.",
            "- Decide whether the paper should be marked `must-cite`, `method-reference`, `background-only`, or `not-relevant`.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
