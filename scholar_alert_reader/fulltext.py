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


@dataclass
class SectionExcerpt:
    key: str
    label: str
    heading: str
    excerpt: str


@dataclass
class EvidenceSignal:
    category: str
    reference: str
    sentence: str


SECTION_ORDER = [
    "abstract",
    "introduction",
    "data",
    "methods",
    "results",
    "discussion",
    "limitations",
    "conclusions",
]

SECTION_LABELS = {
    "abstract": "Abstract / Summary",
    "introduction": "Introduction / Motivation",
    "data": "Data / Study Area",
    "methods": "Methods",
    "results": "Results / Findings",
    "discussion": "Discussion / Interpretation",
    "limitations": "Limitations / Caveats",
    "conclusions": "Conclusions",
}

SECTION_ALIASES = {
    "abstract": "abstract",
    "summary": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "motivation": "introduction",
    "related work": "introduction",
    "study area": "data",
    "geological setting": "data",
    "tectonic setting": "data",
    "data": "data",
    "dataset": "data",
    "datasets": "data",
    "observations": "data",
    "materials": "data",
    "data and methods": "methods",
    "materials and methods": "methods",
    "method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "model": "methods",
    "models": "methods",
    "inversion": "methods",
    "experimental setup": "methods",
    "experiments": "methods",
    "results": "results",
    "result": "results",
    "findings": "results",
    "analysis": "results",
    "discussion": "discussion",
    "interpretation": "discussion",
    "discussion and conclusions": "discussion",
    "limitations": "limitations",
    "limitation": "limitations",
    "caveats": "limitations",
    "uncertainty and limitations": "limitations",
    "conclusion": "conclusions",
    "conclusions": "conclusions",
    "concluding remarks": "conclusions",
}

FIGURE_RE = re.compile(r"\b(?:fig(?:ure)?s?\.?)\s*(?:\(?[sS]?\d+[A-Za-z]?(?:\s*(?:,|and|&|-|to)\s*[sS]?\d+[A-Za-z]?)*\)?)", re.IGNORECASE)
TABLE_RE = re.compile(r"\b(?:table|tab\.)\s*(?:\(?[sS]?\d+[A-Za-z]?(?:\s*(?:,|and|&|-|to)\s*[sS]?\d+[A-Za-z]?)*\)?)", re.IGNORECASE)
SUPPLEMENT_RE = re.compile(r"\b(?:supplementary|supporting information|appendix|supplemental)\b", re.IGNORECASE)
DATA_RE = re.compile(r"\b(?:data availability|data are available|data is available|dataset|repository|zenodo|figshare|dryad|earthscope|iris|nodc|doi:|https?://)\b", re.IGNORECASE)
CODE_RE = re.compile(r"\b(?:code availability|source code|github|gitlab|software|repository|scripts are available|code is available|code are available)\b", re.IGNORECASE)


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


def full_text_pdf_paths(record: dict[str, Any]) -> list[str]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    full_text = metadata.get("full_text") if isinstance(metadata.get("full_text"), dict) else {}
    values = full_text.get("pdf_paths", []) if isinstance(full_text, dict) else []
    if isinstance(values, list):
        return [str(value) for value in values if str(value).strip()]
    if values:
        return [str(values)]
    return []


def first_full_text_path(record: dict[str, Any], explicit_path: Path | None = None) -> Path:
    if explicit_path:
        return explicit_path.expanduser()
    for value in full_text_pdf_paths(record) + zotero_pdf_paths(record):
        path = Path(value).expanduser()
        if path.exists():
            return path
    paths = full_text_pdf_paths(record) + zotero_pdf_paths(record)
    if paths:
        return Path(paths[0]).expanduser()
    raise FileNotFoundError("No local PDF/text path found. Run zotero-sync or fetch-pdf first, or pass --pdf-path.")


def sentence_candidates(full_text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", full_text)
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [part.strip() for part in parts if 80 <= len(part.strip()) <= 420]


def evidence_sentence_candidates(full_text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", full_text)
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [part.strip() for part in parts if 30 <= len(part.strip()) <= 520]


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


def normalize_heading(value: str) -> str:
    value = re.sub(r"^\s*(?:section\s+)?(?:[ivxlcdm]+|\d+)(?:[.\-)]\d+)*[.\-):]?\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[^a-z0-9/& -]+", "", value.lower())
    value = value.replace("&", " and ")
    value = re.sub(r"\s+", " ", value).strip(" -:")
    return value


def detect_section_key(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return None
    if stripped.endswith((".", "?", "!")):
        return None
    if len(stripped.split()) > 9:
        return None
    normalized = normalize_heading(stripped)
    if not normalized:
        return None
    if normalized in SECTION_ALIASES:
        key = SECTION_ALIASES[normalized]
        return key, stripped
    for alias, key in SECTION_ALIASES.items():
        if normalized.startswith(alias + " ") or normalized.endswith(" " + alias):
            return key, stripped
    return None


def section_sentences(section_text: str, profile: dict[str, Any], limit: int = 2) -> list[str]:
    selected = representative_sentences(section_text, profile, limit)
    if selected:
        return selected[:limit]
    return sentence_candidates(section_text)[:limit]


def extract_section_excerpts(full_text: str, max_chars: int = 1000) -> dict[str, SectionExcerpt]:
    sections: dict[str, SectionExcerpt] = {}
    current_key: str | None = None
    current_heading = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_heading, current_lines
        if not current_key:
            current_lines = []
            return
        excerpt = clean_full_text("\n".join(current_lines), max_chars=max_chars)
        if len(excerpt) >= 24:
            previous = sections.get(current_key)
            if previous is None or len(excerpt) > len(previous.excerpt):
                sections[current_key] = SectionExcerpt(
                    key=current_key,
                    label=SECTION_LABELS[current_key],
                    heading=current_heading,
                    excerpt=excerpt,
                )
        current_key = None
        current_heading = ""
        current_lines = []

    for raw_line in full_text.splitlines():
        detected = detect_section_key(raw_line)
        if detected:
            flush()
            current_key, current_heading = detected
            current_lines = []
            continue
        if current_key:
            current_lines.append(raw_line)
    flush()
    return sections


def remove_detected_section_headings(full_text: str) -> str:
    lines = [line for line in full_text.splitlines() if detect_section_key(line) is None]
    return "\n".join(lines)


def extract_visual_data_signals(full_text: str, limit: int = 18) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    seen: set[tuple[str, str, str]] = set()
    patterns = [
        ("Figures", FIGURE_RE),
        ("Tables", TABLE_RE),
        ("Supplement", SUPPLEMENT_RE),
        ("Data Availability", DATA_RE),
        ("Code / Software", CODE_RE),
    ]
    for sentence in evidence_sentence_candidates(full_text):
        for category, pattern in patterns:
            matches = pattern.findall(sentence)
            if not matches:
                continue
            reference = "; ".join(sorted({match.strip() for match in matches if match.strip()}))
            key = (category, reference.lower(), sentence.lower())
            if key in seen:
                continue
            seen.add(key)
            signals.append(EvidenceSignal(category=category, reference=reference, sentence=sentence))
            if len(signals) >= limit:
                return signals
    return signals


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
    analysis_text = remove_detected_section_headings(full_text)
    hits = profile_hits_in_text(analysis_text, profile)
    terms = top_full_text_terms(analysis_text, 16)
    sentences = representative_sentences(analysis_text, profile, 8)
    sections = extract_section_excerpts(full_text)
    visual_data_signals = extract_visual_data_signals(analysis_text)
    abstract = sections.get("abstract").excerpt if sections.get("abstract") else find_section_excerpt(full_text, ["Abstract", "Summary"], max_chars=900)
    methods = sections.get("methods").excerpt if sections.get("methods") else find_section_excerpt(full_text, ["Methods", "Method", "Data and Methods", "Methodology"], max_chars=900)
    conclusions = sections.get("conclusions").excerpt if sections.get("conclusions") else find_section_excerpt(full_text, ["Conclusions", "Conclusion", "Discussion and Conclusions"], max_chars=900)
    found_section_labels = [SECTION_LABELS[key] for key in SECTION_ORDER if key in sections]
    missing_section_labels = [SECTION_LABELS[key] for key in SECTION_ORDER if key not in sections]

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
    lines.extend(["", "## Section Coverage", ""])
    lines.append("- Found: " + ", ".join(found_section_labels) if found_section_labels else "- Found: no standard paper sections detected.")
    lines.append("- Missing or weak: " + ", ".join(missing_section_labels) if missing_section_labels else "- Missing or weak: none of the tracked sections.")
    lines.extend(["", "## Evidence By Section", ""])
    if sections:
        for key in SECTION_ORDER:
            section = sections.get(key)
            if not section:
                continue
            lines.extend([f"### {section.label} Excerpt", "", section.excerpt, "", "Inspection targets:"])
            section_focus = section_sentences(section.excerpt, profile, limit=2)
            if section_focus:
                lines.extend(f"- {sentence}" for sentence in section_focus)
            else:
                lines.append("- Inspect this section manually; no concise sentence candidate was detected.")
            lines.append("")
    else:
        lines.append("- No standard sections were detected. Inspect the full text cache and consider passing a cleaner `.txt` export.")
    if abstract and "abstract" not in sections:
        lines.extend(["", "## Abstract / Summary Excerpt", "", abstract])
    if methods and "methods" not in sections:
        lines.extend(["", "## Methods Excerpt", "", methods])
    if conclusions and "conclusions" not in sections:
        lines.extend(["", "## Conclusion Excerpt", "", conclusions])
    lines.extend(["", "## Sentences To Inspect", ""])
    if sentences:
        lines.extend(f"- {sentence}" for sentence in sentences)
    else:
        lines.append("- No profile-weighted sentences found. Inspect the text cache manually.")
    lines.extend(["", "## Visual, Table, Data, And Code Signals", ""])
    if visual_data_signals:
        for signal in visual_data_signals:
            reference = f" `{signal.reference}`" if signal.reference else ""
            lines.append(f"- **{signal.category}**{reference}: {signal.sentence}")
    else:
        lines.append("- No figure, table, supplement, data availability, or code/software signals were detected in the extracted text.")
    lines.extend(
        [
            "",
            "## Citation Readiness Checklist",
            "",
            "- Problem and claimed contribution: verify from the introduction, abstract, and conclusion before citing.",
            "- Data and study area: verify stations, catalog, region, period, preprocessing, and any selection bias.",
            "- Method assumptions: inspect equations, model parameterization, training/inversion setup, uncertainty treatment, and baselines.",
            "- Main results: check whether figures/tables support the claim you want to cite.",
            "- Visual evidence: inspect the figures and tables flagged above, especially panels tied to your intended citation.",
            "- Limits and failure modes: look for caveats in discussion, limitations, supplement, and data/code availability.",
        ]
    )
    if missing_section_labels:
        lines.extend(["", "## Missing Or Weak Sections", ""])
        lines.extend(f"- {label}" for label in missing_section_labels)
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
